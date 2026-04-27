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
    chat_history: List[Dict[str, str]]
    destination: Optional[str]
    origin: Optional[str]
    days: Optional[int]
    budget: Optional[float]
    travel_month: Optional[str]
    trip_style: Optional[str] # Changed from trip_type to match instruction
    mood: Optional[str] # New field
    travellers: Optional[int]
    food_preference: Optional[str]
    
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
    field_changes: List[str] # To track what changed for stateful feedback
    
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

    # Helper for budget parsing
    def parse_budget(self, text):
        if not text: return None
        text = str(text).lower().replace(",", "")
        match = re.search(r'(\d+)\s*k', text)
        if match:
            return float(match.group(1)) * 1000
        numbers = re.findall(r'\d+', text)
        return float(numbers[0]) if numbers else None

    # Node 1: Parser (Extraction Engine Wrapper)
    def parser(self, state: PlanState) -> PlanState:
        # Since run() now does the extraction, this node ensures 
        # any missing fields that might have been skipped are caught
        # or it can just be a pass-through if run() is thorough.
        return state

    def extract_info(self, query: str, history: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Hybrid Extraction: LLM + Regex Safety Net
        """
        extracted = {
            'destination': None,
            'origin': None,
            'days': None,
            'budget': None,
            'travellers': None,
            'trip_style': None,
            'mood': None
        }

        # 1. LLM Extraction
        if self.llm:
            history_str = "\n".join([f"{m.get('role', 'user').capitalize()}: {m.get('content', '')}" for m in history[-5:]])
            
            prompt = f"""Extract trip details (destination, origin, days, budget, travellers) as a JSON object. 
            If the user mentions a new value, update it. If they don't mention a field, check the history and keep the old value.
            Use null if unknown.

            Chat History:
            {history_str}

            User Query: '{query}'"""
            
            try:
                # Use HumanMessage as requested
                response = self.llm.invoke([HumanMessage(content=prompt)])
                content = response.content if hasattr(response, 'content') else str(response)
                
                # NEW FIX: Extract JSON using Regex in case the LLM adds chatter
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    llm_data = json.loads(json_match.group())
                    for k in extracted.keys():
                        if llm_data.get(k) is not None:
                            extracted[k] = llm_data[k]
                else:
                    print("DEBUG: No JSON found in LLM response")
            except Exception as e:
                print(f"Extraction Error: {e}")

        # 2. Safety Net (Regex & Keyword Scanner) - Fallback for LLM failure
        query_lower = query.lower()
        
        # Days: Match any number followed by 'day' or 'days' (e.g., "3 days")
        if extracted['days'] is None:
            days_match = re.search(r'(\d+)\s*(?:day|days)', query, re.IGNORECASE)
            if days_match:
                extracted['days'] = int(days_match.group(1))

        # Budget: Use parse_budget helper
        if extracted['budget'] is None:
            extracted['budget'] = self.parse_budget(query_lower)

        # Destination: Keyword match against cities.json
        if extracted['destination'] is None:
            cities = self.db.get_all_cities()
            for city in cities:
                if city['name'].lower() in query_lower:
                    extracted['destination'] = city['name']
                    break
        
        # Travellers fallback: Scan for "X people" or similar
        if extracted['travellers'] is None:
            match = re.search(r'(\d+)\s*(people|travellers|person|members)', query_lower)
            if match:
                extracted['travellers'] = int(match.group(1))

        return extracted

    # Node 2: Missing Fields (Validation)
    def check_missing(self, state: PlanState) -> PlanState:
        if state.get('status') == 'greeting':
            return state

        # Mandatory field check - Only Destination is strictly required now
        if not state.get('destination'):
            state['missing_fields'] = ['destination']
            state['status'] = 'gathering'
            state['final_response'] = "I'm excited to help! Which destination are you thinking of for your next trip?"
            return state

        # DEFAULT VALUES: If destination is present, fill missing fields with defaults
        if not state.get('days'): state['days'] = 3
        if not state.get('budget'): state['budget'] = 20000
        if not state.get('travellers'): state['travellers'] = 2
        
        # NO-ASK RULE: Fill secondary defaults
        if not state.get('origin'): state['origin'] = "Chennai"
        if not state.get('travel_month'): state['travel_month'] = "May" 
        if not state.get('trip_style'): state['trip_style'] = "Relaxation"
        if not state.get('mood'): state['mood'] = "Relaxation"
        
        state['status'] = 'planning'
            
        # Resolve City ID
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
        num_travellers = state.get('travellers', 2)
        nights = state.get('days', 3)
        total_budget = state.get('budget', 20000)
        
        # Calculate transport cost for the group (round trip)
        t_cost = state['selected_transport'].get('total_estimated_cost', 0) * num_travellers * 2
        
        best_hotel = self.logic.select_hotel_best_fit(state['city_id'], num_travellers, total_budget, nights, t_cost)
        
        if not best_hotel:
            state['selected_hotel'] = {"name": "Comfort Inn", "price_per_night": 2500, "rating": 4.0, "area": "City Center", "max_people": 2}
        else:
            state['selected_hotel'] = best_hotel
            state['budget_tier'] = best_hotel.get('hotel_type', 'mid')
            
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
        
        if state['trip_style'] == 'couple':
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
        
        # GAP FILLING: Maximize budget if remaining > 20%
        state = self.logic.maximize_plan(state)
        
        if state['costs']['total'] > state['budget']: state['status'] = 'correcting'
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

        # Response Formatting
        changes = state.get('field_changes', [])
        if changes:
            if 'travellers' in changes:
                summary = f"Updated! I've adjusted the plan for {state['travellers']} people. This includes an extra room and updated transport costs.\n\n"
            else:
                summary = f"Updated! I've adjusted your plan based on the new {changes[0].capitalize()} preference.\n\n"
        else:
            summary = f"Got it! Generating your {state['days']}-day {city} trip for {num_travellers} people with a ₹{state['budget']:,} budget.\n\n"
        
        summary += f"Dates: {month} | Weather: {'Rainy' if state.get('is_rainy') else 'Clear'}\n"
        summary += f"Logistics: {transport_summary}\n"
        
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
        """
        FINAL CORE UPGRADE: Logic: Rewrite the run() function. 
        Before doing anything, it must pass the query and chat_history through an extraction step.
        """
        query = input_data.get("query", "")
        history = input_data.get("chat_history") or input_data.get("history") or []
        
        # 1. Extraction Step
        extracted = self.extract_info(query, history)
        
        # 2. Build State
        state: PlanState = {
            "query": query,
            "chat_history": history,
            "destination": extracted.get('destination') or input_data.get('destination'),
            "origin": extracted.get('origin') or input_data.get('origin'),
            "days": extracted.get('days') or input_data.get('days'),
            "budget": extracted.get('budget') or input_data.get('budget'),
            "travel_month": input_data.get("travel_month") or "Suggest by AI",
            "trip_style": extracted.get('trip_style') or input_data.get('trip_style') or input_data.get('trip_type'),
            "mood": extracted.get('mood') or input_data.get('mood'),
            "travellers": extracted.get('travellers') or input_data.get('travellers', 2),
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
            "field_changes": [],
            "final_response": "",
            "status": "gathering",
            "explanation": "",
            "kpi": None,
            "location": None,
            "map_config": None,
            "media_cards": None
        }

        # Track changes for stateful feedback
        # If we have a previous turn, compare extracted vs history-based state
        # (This is simplified; a real system would compare against a stored session state)
        for field in ['days', 'travellers', 'budget', 'destination']:
            old_val = input_data.get(field)
            new_val = state.get(field)
            if old_val and new_val and str(old_val) != str(new_val):
                state['field_changes'].append(field)

        # Debugging: Final Merged State (Brain of the AI)
        print(f"DEBUG: Final Merged State -> {{'dest': state['destination'], 'days': state['days'], 'budget': state['budget'], 'people': state['travellers']}}")

        return self.workflow.invoke(state)