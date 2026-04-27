import math
from typing import List, Dict, Any, Optional

class TravelPlannerLogic:
    def __init__(self, data_service):
        self.db = data_service

    def calculate_proxy_transport_cost(self, origin_coords, dest_coords, tier):
        """
        Fallback Logic: Distance * Rate (₹12 for Bus, ₹28 for Cab)
        """
        if not origin_coords or not dest_coords:
            return 1500 # Safe fallback
            
        lat1, lon1 = origin_coords
        lat2, lon2 = dest_coords
        
        R = 6371 # Radius of Earth in km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        distance = R * c
        
        # Rate: Cab (Luxury) = 28, Bus (Others) = 12
        rate = 28 if tier == 'luxury' else 12
        return max(500, round(distance * rate))

    def select_hotel_best_fit(self, city_id: int, travellers: int, total_budget: float, nights: int, transport_cost: float = 0) -> Optional[Dict[str, Any]]:
        """
        Logic: Stop picking the cheapest option.
        If (Hotel + Transport) < 50% of the User Budget, automatically upgrade the hotel_type to 'luxury'.
        """
        hotels = self.db.get_hotels(city_id)
        if not hotels: return None
        
        # Calculate rooms needed
        def get_rooms(h):
            max_p = h.get('max_people', 2)
            if not max_p or max_p <= 0: max_p = 2
            return math.ceil(travellers / max_p)

        # Separate by tier
        luxury_hotels = [h for h in hotels if h.get('hotel_type', '').lower() == 'luxury']
        mid_hotels = [h for h in hotels if h.get('hotel_type', '').lower() == 'mid']
        budget_hotels = [h for h in hotels if h.get('hotel_type', '').lower() == 'budget']

        # Rule: Check if we should force luxury
        # Calculate baseline stay cost using a mid-tier hotel (or budget if mid is unavailable)
        baseline_hotel = (mid_hotels + budget_hotels)[0] if (mid_hotels + budget_hotels) else hotels[0]
        baseline_stay_cost = (baseline_hotel.get('price_per_night', 0) * get_rooms(baseline_hotel) * nights)
        
        # If the stay cost is under 40% of the user budget, force luxury to maximize value
        force_luxury = False
        if baseline_stay_cost < (total_budget * 0.4):
            force_luxury = True
            
        if force_luxury and luxury_hotels:
            # Pick the best luxury hotel that fits the overall budget (including transport)
            luxury_hotels.sort(key=lambda x: x.get('rating', 0), reverse=True)
            for h in luxury_hotels:
                h_total_stay = h.get('price_per_night', 0) * get_rooms(h) * nights
                if (h_total_stay + transport_cost) <= total_budget:
                    return h
        
        # If not forcing luxury or no luxury fits, pick the best fit from others
        # We want to use the budget, so we sort by stay cost DESCENDING within the affordable range
        affordable = []
        for h in hotels:
            h_total_stay = h.get('price_per_night', 0) * get_rooms(h) * nights
            if (h_total_stay + transport_cost) <= total_budget:
                affordable.append(h)
        
        if affordable:
            # Sort by total stay cost descending to maximize budget usage
            affordable.sort(key=lambda x: (x.get('price_per_night', 0) * get_rooms(x) * nights), reverse=True)
            return affordable[0]

        # Final fallback
        hotels.sort(key=lambda x: x.get('price_per_night', 99999))
        return hotels[0] if hotels else None

    def maximize_plan(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Instruction: "If Total_Cost < 60% of Budget, upgrade the hotel tier (Budget -> Mid -> Luxury) 
        and add premium attractions until the money is used up to 90%."
        """
        total_budget = state['budget']
        costs = state.get('costs', {})
        current_total = costs.get('total', 0)
        travellers = state.get('travellers', 1)
        days = state.get('days', 1)
        city_id = state['city_id']

        # If spent < 60%, we start upgrading aggressively
        if current_total < (total_budget * 0.6):
            # 1. Upgrade Food to Fine Dining
            food_places = self.db.get_food_places(city_id)
            if food_places:
                # Filter for "Fine Dining" or high cost
                fine_dining = [f for f in food_places if f.get('avg_cost', 0) >= 1000 or 'fine' in f.get('name', '').lower()]
                if not fine_dining:
                    fine_dining = sorted(food_places, key=lambda x: x.get('avg_cost', 0), reverse=True)
                
                # Replace existing recommendations with better ones
                new_recs = []
                for i in range(days * 2):
                    f = fine_dining[i % len(fine_dining)]
                    new_recs.append({
                        **f,
                        "detail": f"Fine Dining at {f['name']} — enjoy a premium culinary experience"
                    })
                state['food_recommendations'] = new_recs
                
                # Update food cost
                total_f_cost = sum(f.get('avg_cost', 500) for f in new_recs) * travellers
                costs['food'] = total_f_cost
                
            # 2. Add Premium Attractions
            all_attractions = self.db.get_attractions(city_id)
            if all_attractions:
                # Sort by cost descending (Premium)
                premium_acts = sorted(all_attractions, key=lambda x: x.get('cost', 0), reverse=True)
                
                # Iteratively add to itinerary until 90% budget is used
                for day in state['itinerary_days']:
                    for act in premium_acts:
                        # Recalculate total spent
                        current_spent = sum([v for k, v in costs.items() if k not in ['total', 'per_person']])
                        if current_spent >= (total_budget * 0.9):
                            break
                        
                        # Don't repeat activities
                        already_in = False
                        for d in state['itinerary_days']:
                            if any(a.get('name') == act.get('name') for a in d.get('activities', [])):
                                already_in = True
                                break
                        
                        if not already_in:
                            day['activities'].append(act)
                            day['evening'] += f" | Nightcap: {act['name']} (Premium Experience)."
                            costs['activities'] += act.get('cost', 100) * travellers
                            
                    if sum([v for k, v in costs.items() if k not in ['total', 'per_person']]) >= (total_budget * 0.9):
                        break

            # Recalculate total
            costs['total'] = sum([v for k, v in costs.items() if k not in ['total', 'per_person']])
            costs['per_person'] = costs['total'] / travellers if travellers > 0 else costs['total']
            state['costs'] = costs
            
        return state

    def score_months(self, weather_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        scored = []
        for w in weather_list:
            score = 0
            temp_type = w.get('temperature_type', 'pleasant').lower()
            is_rainy = w.get('rainy', False)
            if temp_type == 'pleasant': score += 50
            elif temp_type == 'cool': score += 30
            elif temp_type == 'hot': score += 10
            else: score += 20
            if not is_rainy: score += 50
            else: score += 10
            scored.append({**w, "weather_score": score})
        return sorted(scored, key=lambda x: x['weather_score'], reverse=True)

    def filter_attractions(self, attractions: List[Dict[str, Any]], weather: Dict[str, Any], preferences: Dict[str, Any]) -> List[Dict[str, Any]]:
        is_rainy = weather.get('condition', '').lower() in ['rainy', 'heavy rain', 'monsoon']
        filtered = []
        for attr in attractions:
            if is_rainy and attr.get('type') == 'Outdoor': continue
            filtered.append(attr)
        return filtered

    def generate_itinerary(self, days: int, attractions: List[Dict[str, Any]], hotel: Dict[str, Any], num_rooms: int, num_travellers: int, mood: str = "Relaxation") -> List[Dict[str, Any]]:
        """
        MISSION: DAY-WISE FLAT STRUCTURE
        - Stop using morning, afternoon, evening slots.
        - Create a consolidated activities_list.
        - Ensure 100% data availability with Modulo Logic.
        """
        pool = attractions.copy()
        if mood.lower() == 'adventure':
            pool.sort(key=lambda x: (x.get('outdoor', False), x.get('cost', 0)), reverse=True)
        else:
            pool.sort(key=lambda x: (x.get('outdoor', True), x.get('duration', 99)))
            
        itinerary = []
        for i in range(days):
            # Select 3 unique activities per day using modulo
            m_spot = pool[(i * 3) % len(pool)]
            a_spot = pool[(i * 3 + 1) % len(pool)]
            e_spot = pool[(i * 3 + 2) % len(pool)]
            
            day_acts = [m_spot, a_spot, e_spot]
            activities_list = [
                f"Visit {m_spot['name']} in {m_spot.get('area', 'Central Area')}",
                f"Explore {a_spot['name']} ({a_spot.get('area', 'General Area')})",
                f"Evening at {e_spot['name']} — Enjoy the local vibe"
            ]
            
            itinerary.append({
                "day": i + 1,
                "activities_list": activities_list,
                "activities": day_acts,
                "stay": hotel['name'],
                "meal": "Breakfast at Hotel, Lunch & Dinner at Local Restaurants",
                "area": m_spot.get('area', 'Main Area')
            })
            
        return itinerary

    def group_activities_by_area(self, attractions: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        areas = {}
        for attr in attractions:
            area = attr.get('area', 'General')
            if area not in areas: areas[area] = []
            areas[area].append(attr)
        return areas