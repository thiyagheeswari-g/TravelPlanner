import os
import json
import re
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from database import DataService
from planner import TravelPlannerLogic
from langchain_huggingface import HuggingFaceEndpoint
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

load_dotenv()

class PlanState(TypedDict):
    # Inputs
    query: str
    destination: Optional[str]
    origin: Optional[str]
    days: Optional[int]
    budget: Optional[float]
    travel_month: Optional[str]
    trip_type: Optional[str]
    travellers: Optional[int]
    food_preference: Optional[str] # New field
    
    # Processed Data
    city_id: Optional[int]
    weather_data: Optional[Dict[str, Any]]
    is_rainy: bool
    
    # Selections
    selected_hotel: Optional[Dict[str, Any]]
    selected_transport: Optional[Dict[str, Any]]
    food_recommendations: Optional[List[Dict[str, Any]]]
    itinerary_days: Optional[List[Dict[str, Any]]]
    
    # Validation
    costs: Optional[Dict[str, float]]
    missing_fields: List[str]
    budget_tier: str # luxury, mid, budget
    
    # Outputs
    final_response: str
    status: str
    explanation: str
    kpi: Optional[Dict[str, Any]]
    location: Optional[Dict[str, Any]]
    media_cards: Optional[Dict[str, Any]]
    map_config: Optional[Dict[str, Any]]

class TravelAgent:
    def __init__(self, db: Optional[DataService] = None):
        self.db = db if db else DataService()
        self.logic = TravelPlannerLogic(self.db)
        
        # Initialize Hugging Face LLM (Mistral-7B)
        hf_token = os.getenv("HUGGINGFACEHUB_API_TOKEN")
        if hf_token:
            repo_id = "mistralai/Mistral-7B-Instruct-v0.2"
            self.llm = HuggingFaceEndpoint(
                repo_id=repo_id,
                huggingfacehub_api_token=hf_token,
                temperature=0.1,
                max_new_tokens=512,
                task="conversational"
            )

        else:
            self.llm = None
            
        self.workflow = self._build_workflow()

    def _build_workflow(self):
        builder = StateGraph(PlanState)

        builder.add_node("parser", self.parser) # Node 1
        builder.add_node("check_missing", self.check_missing) # Node 2
        builder.add_node("weather_filter", self.weather_filter) # Node 3
        builder.add_node("hotel_selector", self.hotel_selector) # Node 4
        builder.add_node("transport_selector", self.transport_selector) # Node 5
        builder.add_node("food_selector", self.food_selector) # Node 6
        builder.add_node("budget_validator", self.budget_validator) # Node 7
        builder.add_node("self_correction", self.self_correction) # Node 8
        builder.add_node("formatter", self.formatter)

        builder.set_entry_point("parser")
        
        builder.add_edge("parser", "check_missing")
        
        builder.add_conditional_edges(
            "check_missing",
            lambda x: "continue" if x['status'] == 'planning' else "end",
            {
                "continue": "weather_filter",
                "end": END
            }
        )

        builder.add_edge("weather_filter", "transport_selector")
        builder.add_edge("transport_selector", "hotel_selector")
        builder.add_edge("hotel_selector", "food_selector")
        builder.add_edge("food_selector", "budget_validator")
        
        builder.add_conditional_edges(
            "budget_validator",
            lambda x: "correct" if x['status'] == 'correcting' else "format",
            {
                "correct": "self_correction",
                "format": "formatter"
            }
        )
        
        builder.add_edge("self_correction", "formatter")
        builder.add_edge("formatter", END)

        return builder.compile()

    # Node 1: Parser
    def parser(self, state: PlanState) -> PlanState:
        query = state.get('query', '').lower().strip()
        
        # PRIORITIZE EXPLICIT INPUTS (from sidebar/frontend)
        # This prevents "hallucinations" of the wrong city when Vellore is selected.
        if state.get('destination'):
            state['destination'] = state['destination']
        if state.get('origin'):
            state['origin'] = state['origin']
        
        # Handle Greetings
        greetings = ["hi", "hello", "hey", "greetings", "good morning", "good evening"]
        if any(query == g for g in greetings):
            state['status'] = 'greeting'
            state['final_response'] = "Hi there! I'm your professional travel assistant. I can help you plan trips across Tamil Nadu, Kerala, Karnataka, Andhra Pradesh, and Telangana. Where would you like to go?"
            return state

        # Dynamic Extraction using cities.json + Common Origins
        cities = self.db.get_all_cities()
        common_origins = ["chennai", "bangalore", "mumbai", "delhi", "hyderabad", "kochi", "coimbatore", "madurai", "vizag", "visakhapatnam"]
        
        # 1. Identify Destination (Only if missing)
        if not state.get('destination'):
            for city in cities:
                if city['name'].lower() in query:
                    state['destination'] = city['name']
                    break
        
        # 2. Identify Origin (Only if missing)
        if not state.get('origin'):
            # Check against cities.json first
            for city in cities:
                if city['name'].lower() in query and city['name'] != state.get('destination'):
                    state['origin'] = city['name']
                    break
        
            # Fallback for common origins not in our destination dataset
            if not state.get('origin'):
                for city in common_origins:
                    if city in query:
                        state['origin'] = city.capitalize()
                        break
        
        # 3. Days extraction
        match_days = re.search(r'(\d+)\s*(-)?\s*day', query)
        if match_days: 
            state['days'] = int(match_days.group(1))
            
        # 4. Budget extraction
        match_budget = re.search(r'(?:budget|under|₹|rs\.?)\s*(\d+)(k|000)?', query)
        if not match_budget:
            match_budget = re.search(r'(\d+)\s*(k|000)', query)
            
        if match_budget:
            val = int(match_budget.group(1))
            suffix = match_budget.group(2)
            if suffix == 'k': val *= 1000
            elif suffix == '000': val = val 
            if val > 1000: state['budget'] = float(val)

        # 5. Month extraction
        months = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december',
                  'jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
        for m in months:
            if f" {m}" in f" {query}" or f"{m} " in f"{query} ":
                # Map full names to short names if needed, but our weather.json uses short? 
                # Let's check weather.json again. It uses Jan, Feb, etc.
                short_m = m[:3].capitalize()
                state['travel_month'] = short_m
                break

        # 6. Trip type extraction
        if "solo" in query: state['trip_type'] = "solo"
        elif any(w in query for w in ["couple", "partner", "romantic", "honeymoon"]): state['trip_type'] = "couple"
        elif "family" in query: state['trip_type'] = "family"
        elif any(w in query for w in ["friends", "group"]): state['trip_type'] = "friends"

        # LLM Overwrite/Fill (if available)
        if self.llm:
            prompt = f"<s>[INST] Extract travel intent from: '{query}'. Return ONLY raw JSON: {{\"destination\": string, \"origin\": string, \"days\": int, \"budget\": float, \"travel_month\": string, \"trip_type\": \"solo\"|\"couple\"|\"family\"|\"friends\", \"travellers\": int}}. Use null for missing. [/INST]</s>"
            try:
                res = self.llm.invoke(prompt)
                match = re.search(r'\{.*\}', res, re.DOTALL)
                if match:
                    extracted = json.loads(match.group())
                    for k, v in extracted.items():
                        if v: state[k] = v # Prioritize LLM extraction
            except Exception as e:
                print(f"Parser LLM Error: {e}")

        return state

    # Node 2: Missing Fields
    def check_missing(self, state: PlanState) -> PlanState:
        if state.get('status') == 'greeting':
            return state

        required = ['origin', 'destination', 'travel_month', 'trip_type', 'days', 'budget']
        missing = [f for f in required if not state.get(f)]
        
        if missing:
            state['missing_fields'] = missing
            state['status'] = 'gathering'
            
            dest = state.get('destination')
            if dest:
                msg = f"{dest} is a fantastic choice! To plan the best route and activities, could you please tell me "
                parts = []
                if 'origin' in missing: parts.append("which city you'll be traveling from")
                if 'travel_month' in missing: parts.append("which month you're planning for")
                if 'trip_type' in missing: parts.append("if this is a solo trip, or if you're traveling with a partner or friends")
                if 'days' in missing: parts.append("how many days you'd like to spend there")
                if 'budget' in missing: parts.append("what your total budget is")
                
                if len(parts) > 1:
                    msg += ", ".join(parts[:-1]) + " and " + parts[-1] + "?"
                elif parts:
                    msg += parts[0] + "?"
                else:
                    msg = f"I'm excited to help! I just need a few more details: {', '.join(missing)}."
            else:
                msg = "Hi! I'd love to help you plan a trip. Which beautiful destination in South India are you considering?"
            
            state['final_response'] = msg
        else:
            state['status'] = 'planning'
            
        # Resolve City ID
        if state.get('destination'):
            city = self.db.get_city_by_name(state['destination'])
            if city:
                state['city_id'] = city['city_id']
            else:
                state['status'] = 'gathering'
                state['final_response'] = f"I'm sorry, I couldn't find {state['destination']} in our registry. We cover major cities in Tamil Nadu, Kerala, Karnataka, Andhra Pradesh, and Telangana."
                
        return state

    # Node 3: Weather Filter
    def weather_filter(self, state: PlanState) -> PlanState:
        city_id = state['city_id']
        month = state['travel_month']
        
        # AI Suggestion Logic (Rule 5: Flexible Mode)
        if month == "Suggest by AI":
            all_weather = self.db.get_all_weather(city_id)
            # Find first month where rainy: false and temperature_type: cool/pleasant
            best_month = next((w for w in all_weather if not w['rainy'] and w['temperature_type'] in ['pleasant', 'cool']), None)
            if not best_month:
                best_month = next((w for w in all_weather if not w['rainy']), all_weather[0])
            
            state['travel_month'] = best_month['month']
            month = best_month['month']
            state['weather_data'] = best_month
            state['explanation'] = f"I've selected {month} because the weather is {best_month['temperature_type']} with no predicted rainfall, making it the perfect time for your trip."
        else:
            weather = self.db.get_weather(city_id, month)
            state['weather_data'] = weather
            if weather and weather.get('rainy'):
                state['explanation'] = f"Note: {month} is a rainy month in {state['destination']}. I have optimized your itinerary with indoor attractions and comfortable stays."
            
        state['is_rainy'] = state['weather_data'].get('rainy', False) if state['weather_data'] else False
        return state

    # Node 5: Transport Selector
    def transport_selector(self, state: PlanState) -> PlanState:
        origin = state['origin']
        dest = state['destination']
        
        # Determine current tier
        if not state.get('budget_tier'):
            budget_per_person = state['budget'] / max(state.get('travellers', 1), 1)
            if budget_per_person < 5000: state['budget_tier'] = 'budget'
            elif budget_per_person > 15000: state['budget_tier'] = 'luxury'
            else: state['budget_tier'] = 'mid'
            
        tier = state.get('budget_tier', 'mid')
        
        routes = self.db.get_transport(origin, dest)
        if routes:
            # We assume routes[0] is the direct route if available
            route = routes[0]
            options = route.get('options', [])
            
            # Tier Mapping Logic
            luxury_types = ['Luxury Volvo', '2AC', '1AC', 'Cab', 'Sedan', 'First Class']
            mid_types = ['3AC (3A)', '3AC', 'AC Sleeper', 'AC Seater', 'Chair Car (CC)', 'AC Deluxe']
            budget_types = ['Sleeper (SL)', 'Sleeper', 'Non-AC Seater', 'Bus', 'Standard']
            
            # Select target types based on tier
            if tier == 'luxury': target_types = luxury_types + mid_types + budget_types
            elif tier == 'mid': target_types = mid_types + budget_types
            else: target_types = budget_types
            
            selected_option = None
            # Filter and Sort: Best in tier
            filtered_options = [o for o in options if any(t.lower() in o.get('type', '').lower() for t in target_types)]
            if not filtered_options: filtered_options = options # Fallback
            
            # Sort by cost ascending for budget, descending for luxury (within tier)
            if tier == 'luxury':
                filtered_options.sort(key=lambda x: x.get('cost', 9999), reverse=True)
            else:
                filtered_options.sort(key=lambda x: x.get('cost', 9999))
                
            selected_option = filtered_options[0]
            
            transport_detail = f"Board {selected_option.get('mode', 'Transport')} ({selected_option.get('type', 'Standard')}) provided by {selected_option.get('provider', 'Local Provider')}."
            if selected_option.get('departure_time'):
                transport_detail += f" Departure at {selected_option['departure_time']}."

            state['selected_transport'] = {
                "mode": selected_option.get('mode'),
                "type": selected_option.get('type'),
                "train_name": selected_option.get('train_name', selected_option.get('mode')),
                "train_number": selected_option.get('train_number', 'N/A'),
                "departure_time": selected_option.get('departure_time', 'Flexible'),
                "arrival_time": selected_option.get('arrival_time', 'N/A'),
                "duration_hours": selected_option.get('duration_hours', 0),
                "total_estimated_cost": selected_option.get('cost', 500),
                "from_station": route.get('from_station', origin),
                "to_station": route.get('to_station', dest),
                "class": selected_option.get('type'),
                "detail": transport_detail,
                "interchange": False
            }
        else:
            # INTERCHANGE OR FALLBACK
            state['selected_transport'] = {
                "train_name": "Regional Express", 
                "total_estimated_cost": 750 if tier == 'luxury' else (450 if tier == 'mid' else 250), 
                "class": "Standard",
                "detail": f"Board Regional Express/Bus from {origin} to {dest}.",
                "interchange": False
            }
                
        return state
                
        return state


    # Node 4: Hotel Selector
    def hotel_selector(self, state: PlanState) -> PlanState:
        hotels = self.db.get_hotels(state['city_id'])
        if not hotels:
            state['selected_hotel'] = {"name": "Comfort Inn", "price_per_night": 2500, "rating": 4.0, "area": "City Center", "max_people": 2}
            return state

        # Tiered Selection: Set budget_tier based on budget per person (if not already locked by self-correction)
        if not state.get('budget_tier'):
            budget_per_person = state['budget'] / max(state.get('travellers', 1), 1)
            if budget_per_person < 5000:
                state['budget_tier'] = 'budget'
            elif budget_per_person > 10000:
                state['budget_tier'] = 'luxury'
            else:
                state['budget_tier'] = 'mid'
            
        # Hard Budget Cap: (Hotel Price x Rooms x Nights) + (Transport Cost x People x 2) <= 70% of total budget
        import math
        num_travellers = state.get('travellers', 1)
        nights = state['days']
        total_budget = state['budget']
        
        # Pull Transport Cost for the check
        transport = state.get('selected_transport', {})
        t_cost_total = (transport.get('total_estimated_cost', 0) * num_travellers) * 2
        
        cap = total_budget * 0.7
        
        best_hotel = None
        current_tier = state.get('budget_tier', 'luxury')
        tiers_to_try = ['luxury', 'mid', 'budget']
        
        # Start from current tier or higher
        if current_tier in tiers_to_try:
            start_idx = tiers_to_try.index(current_tier)
            tiers_to_try = tiers_to_try[start_idx:]
            
        for t in tiers_to_try:
            tier_hotels = [h for h in hotels if h.get('hotel_type') == t]
            if not tier_hotels: continue
            
            # Sort by price within tier
            tier_hotels.sort(key=lambda x: x.get('price_per_night', 99999))
            
            for h in tier_hotels:
                max_p = h.get('max_people', 2)
                rooms = math.ceil(num_travellers / max_p)
                h_total = h.get('price_per_night', 0) * rooms * nights
                
                if (h_total + t_cost_total) <= cap:
                    best_hotel = h
                    state['budget_tier'] = t
                    break
            
            if best_hotel: break
            
        if not best_hotel:
            # Fallback to the absolute cheapest across all tiers if none fit the 60% cap
            hotels.sort(key=lambda x: x.get('price_per_night', 99999))
            best_hotel = hotels[0]
            # DO NOT reset budget_tier here to avoid recursion loops with self_correction

        state['selected_hotel'] = best_hotel
        return state

    # Node 6: Food Selector
    def food_selector(self, state: PlanState) -> PlanState:
        food = self.db.get_food_places(state['city_id'])
        
        if not food:
            food = [{"name": "Local Market", "cuisine": "Local Street Food", "avg_cost": 250, "rating": 4.2, "area": "City Center"}]
        
        # Apply Food Preference [Veg], [Non-Veg], [Both]
        pref = state.get('food_preference', 'Both')
        if pref == 'Veg':
            food = [f for f in food if 'vegetarian' in f.get('cuisine', '').lower() or 'veg' in f.get('cuisine', '').lower()]
        elif pref == 'Non-Veg':
            food = [f for f in food if 'non-veg' in f.get('cuisine', '').lower() or 'meat' in f.get('cuisine', '').lower()]

        # Relational Sinking: Prioritize food places in the same area as the hotel
        hotel = state.get('selected_hotel')
        hotel_area = hotel.get('area') if hotel else None
        
        if hotel_area:
            local_food = [f for f in food if f.get('area') == hotel_area]
            if local_food:
                food = local_food
        
        if state['trip_type'] == 'couple':
            food.sort(key=lambda x: x.get('rating', 0), reverse=True)
            
        # Rule 4 Formatting: "Lunch at [name] — enjoy authentic [cuisine] cuisine"
        formatted_food = []
        for f in food:
            cuisine = f.get('cuisine', 'Local')
            formatted_food.append({
                **f,
                "detail": f"Meal at {f['name']} — enjoy authentic {cuisine} cuisine"
            })
            
        state['food_recommendations'] = formatted_food[:state['days'] * 2] # 2 per day
        return state

    # Node 7: Budget Validator
    def budget_validator(self, state: PlanState) -> PlanState:
        city_id = state['city_id']
        all_attractions = self.db.get_attractions(city_id)
        food_places = self.db.get_food_places(city_id)
        
        # Weather-Aware
        if state.get('is_rainy'):
            pool = [a for a in all_attractions if not a.get('outdoor', True)]
            if not pool: pool = all_attractions
        else:
            pool = all_attractions

        used_ids = set()
        visited_areas = set()
        itinerary = []
        activity_cost = 0
        
        hotel = state['selected_hotel']
        num_travellers = state.get('travellers', 1)
        max_p = hotel.get('max_people', 2)
        if not max_p or max_p <= 0: max_p = 2
        num_rooms = (num_travellers + max_p - 1) // max_p
        
        def pick_spot(exclude_ids, exclude_areas=None, outdoor_only=False):
            candidates = [a for a in pool if a.get('att_id', a.get('name')) not in exclude_ids]
            if outdoor_only:
                candidates = [a for a in candidates if a.get('outdoor', False)]
            
            if exclude_areas:
                filtered = [a for a in candidates if a.get('area') not in exclude_areas]
                if filtered: candidates = filtered
            
            if not candidates: return None
            return candidates[0]

        for i in range(state['days']):
            # 1. Morning Slot
            morning_spot = pick_spot(used_ids)
            morning_area = morning_spot.get('area') if morning_spot else None
            if morning_spot: 
                used_ids.add(morning_spot.get('att_id', morning_spot.get('name')))
                if morning_area: visited_areas.add(morning_area)
            
            # 2. Afternoon Slot: Must be OUTDOOR and DIFFERENT area
            afternoon_spot = pick_spot(used_ids, exclude_areas=[morning_area] if morning_area else [], outdoor_only=True)
            afternoon_area = afternoon_spot.get('area') if afternoon_spot else None
            if afternoon_spot: 
                used_ids.add(afternoon_spot.get('att_id', afternoon_spot.get('name')))
                if afternoon_area: visited_areas.add(afternoon_area)
            
            # 3. Evening Slot: Different area from morning/afternoon. Fallback to food_place
            exclude_today = []
            if morning_area: exclude_today.append(morning_area)
            if afternoon_area: exclude_today.append(afternoon_area)
            
            evening_spot = pick_spot(used_ids, exclude_areas=exclude_today)
            is_food_fallback = False
            
            if not evening_spot:
                # Fallback to food_place area that hasn't been visited yet (global)
                food_fallback = [f for f in food_places if f.get('area') not in visited_areas]
                if not food_fallback: # Emergency fallback: different from today
                    food_fallback = [f for f in food_places if f.get('area') not in exclude_today]
                
                if food_fallback:
                    evening_spot = food_fallback[0]
                    is_food_fallback = True
            
            if evening_spot:
                if not is_food_fallback:
                    used_ids.add(evening_spot.get('att_id', evening_spot.get('name')))
                if evening_spot.get('area'):
                    visited_areas.add(evening_spot['area'])

            # Formatting
            morning_str = f"Visit {morning_spot['name']} in the {morning_spot['area']} area." if morning_spot else "Leisurely morning walk."
            afternoon_str = f"Explore {afternoon_spot['name']} ({afternoon_spot['area']}) — Perfect outdoor spot." if afternoon_spot else "Relaxing afternoon near the stay."
            
            if evening_spot:
                if is_food_fallback:
                    evening_str = f"Visit the local food hub in {evening_spot['area']} — explore {evening_spot['name']}."
                else:
                    evening_str = f"Experience {evening_spot['name']} in the {evening_spot['area']} district."
            else:
                evening_str = "Quiet evening stroll."

            day_acts = [s for s in [morning_spot, afternoon_spot, evening_spot if not is_food_fallback else None] if s]
            activity_cost += sum(a.get('cost', 50) for a in day_acts)
            
            itinerary.append({
                "day": i + 1,
                "morning": morning_str,
                "afternoon": afternoon_str,
                "evening": evening_str,
                "meal": state['food_recommendations'][i % len(state['food_recommendations'])]['detail'] if state['food_recommendations'] else "Dinner at a local restaurant.",
                "stay": f"Check in to {hotel['name']} ({hotel['rating']}★) — {num_rooms} Rooms booked for {num_travellers} People.",
                "area": morning_area or "Central",
                "activities": day_acts
            })

        state['itinerary_days'] = itinerary
        
        # Sum costs
        t_cost_per_person = state['selected_transport'].get('total_estimated_cost', 0)
        t_cost = (t_cost_per_person * num_travellers) * 2 
        h_cost = hotel.get('price_per_night', 0) * num_rooms * state['days']
        f_cost = 300 * state['days'] * num_travellers 
        act_total_cost = activity_cost * num_travellers
        
        total = h_cost + t_cost + f_cost + act_total_cost
        state['costs'] = {
            "hotel": h_cost, "transport": t_cost, "food": f_cost, "activities": act_total_cost, "total": total,
            "per_person": total / num_travellers if num_travellers > 0 else total
        }
        
        if total > state['budget']: state['status'] = 'correcting'
        else: state['status'] = 'done'
        return state


    # Node 8: Self-Correction (Strict Tiered Optimizer)
    def self_correction(self, state: PlanState) -> PlanState:
        if state['status'] != 'correcting': return state
        
        tiers = ['luxury', 'mid', 'budget']
        current_tier = state.get('budget_tier', 'luxury')
        
        try:
            idx = tiers.index(current_tier)
            if idx < len(tiers) - 1:
                # Downgrade tier strictly
                next_tier = tiers[idx + 1]
                state['budget_tier'] = next_tier
                print(f"--- BUDGET EXCEEDED: Downgrading to {next_tier} tier ---")
                
                # RE-FETCH DATA for both transport and hotel
                state = self.transport_selector(state)
                state = self.hotel_selector(state)
                
                # Recalculate everything
                state = self.budget_validator(state)
                
                # Recursive call if still over budget
                if state['status'] == 'correcting':
                    return self.self_correction(state)
            else:
                # If already at 'budget' tier and still over, force cheapest available
                state['status'] = 'done'
                state['explanation'] = "I've optimized this plan to the absolute minimum budget possible."
        except ValueError:
            state['budget_tier'] = 'budget'
            
        state['status'] = 'done'
        return state


    def formatter(self, state: PlanState) -> PlanState:
        city = state['destination']
        month = state['travel_month']
        transport = state['selected_transport']
        costs = state['costs']
        num_travellers = state.get('travellers', 1)
        hotel = state['selected_hotel']
        
        # Rule 1 Header
        header = f"Journey to {city}"
        
        # Rule 2 Transport
        from_st = transport.get('from_station', state['origin'])
        to_st = transport.get('to_station', city)
        t_name = transport.get('train_name', 'Local Transport')
        t_num = transport.get('train_number', '')
        t_class = transport.get('class', 'Sleeper')
        dep = transport.get('departure_time', 'N/A')
        arr = transport.get('arrival_time', 'N/A')
        
        transport_summary = f"Transport (Board {t_name} from {from_st} to {to_st}) | {dep} - {arr} | Class: {t_class}"
        
        # Fetch coords from city object if available, else fallback to predefined
        city_obj = self.db.get_city_by_name(city)
        if city_obj and 'lat' in city_obj and 'lng' in city_obj:
            city_center = [city_obj['lat'], city_obj['lng']]
        else:
            city_center = self.db.get_coordinates('city', state.get('city_id', 100))
            
        # Summary
        summary = f"{header}\n\n"
        summary += f"Dates: {month} | Travellers: {num_travellers} | Weather: {'Rainy' if state.get('is_rainy') else 'Clear'}\n\n"
        summary += f"Logistics: {transport_summary}\n"
        status_text = "Under Budget" if costs['total'] <= state['budget'] else "Adjusted to Fit"
        summary += f"Budget Summary: ₹{costs['total']:,} ({status_text}). Remaining: ₹{(state['budget'] - costs['total']):,}.\n"

        # KPI Data for Real-time update
        state['kpi'] = {
            "total_budget": state['budget'],
            "spent": costs['total'],
            "remaining": state['budget'] - costs['total']
        }

        # Fetch coords from city object if available, else fallback to predefined
        city_obj = self.db.get_city_by_name(city)
        if city_obj and 'lat' in city_obj and 'lng' in city_obj:
            city_center = [city_obj['lat'], city_obj['lng']]
        else:
            city_center = self.db.get_coordinates('city', state.get('city_id', 100))
        
        state['location'] = {
            "city": city,
            "coords": city_center,
            "zoom": 13
        }

        # Dynamic Markers mapping
        markers = []
        for day in state['itinerary_days']:
            for act in day.get('activities', []):
                markers.append({
                    "name": act.get('name'),
                    "area": act.get('area'),
                    "coords": act.get('coords', city_center)
                })
        
        hotel['coords'] = self.db.get_coordinates('city', state.get('city_id', 100)) # Approximation
        markers.append({
            "name": hotel.get('name'),
            "area": hotel.get('area'),
            "coords": hotel['coords']
        })

        state['map_config'] = {
            "center": city_center,
            "zoom": 13,
            "markers": markers
        }

        # Media Cards Data
        state['media_cards'] = {
            "stays": [hotel],
            "restaurants": state.get('food_recommendations', [])[:4]
        }

        state['final_response'] = summary
        state['status'] = 'done'
        return state

    def run(self, input_data: Dict[str, Any]):
        state: PlanState = {
            "query": input_data.get("query", ""),
            "destination": input_data.get("destination"),
            "origin": input_data.get("origin"),
            "days": int(input_data.get("days", 3)),
            "budget": float(input_data.get("budget", 20000)),
            "travel_month": input_data.get("travel_month"),
            "trip_type": input_data.get("trip_type"),
            "travellers": int(input_data.get("travellers", 1)),
            "food_preference": input_data.get("food_preference", "Both"),
            "city_id": None,
            "weather_data": None,
            "is_rainy": False,
            "selected_hotel": None,
            "selected_transport": None,
            "food_recommendations": [],
            "itinerary_days": [],
            "costs": {},
            "missing_fields": [],
            "budget_tier": None,
            "final_response": "",
            "status": "gathering",
            "explanation": "",
            "kpi": None,
            "location": None,
            "map_config": None,
            "media_cards": None
        }

        return self.workflow.invoke(state)
