import math
import random
from typing import List, Dict, Any, Optional

class TravelPlannerLogic:
    def __init__(self, data_service):
        self.db = data_service

    def calculate_proxy_transport_cost(self, origin_coords, dest_coords, tier):
        if not origin_coords or not dest_coords:
            return 1500 
        lat1, lon1 = origin_coords
        lat2, lon2 = dest_coords
        R = 6371 
        dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return max(500, round(R * c * 15))

    def _jitter_coords(self, lat: float, lng: float, intensity: float = 0.01) -> Dict[str, float]:
        """Creates a small offset to ensure markers don't overlap perfectly."""
        return {
            "lat": lat + (random.uniform(-intensity, intensity)),
            "lng": lng + (random.uniform(-intensity, intensity))
        }

    def select_hotel_best_fit(self, city_id: int, travellers: int, total_budget: float, nights: int, transport_cost: float = 0) -> Optional[Dict[str, Any]]:
        # 5. BUFFER RESERVE: Reserve 10% of budget for emergencies
        usable_budget = total_budget * 0.9
        
        hotels = self.db.get_hotels(city_id)
        location_name = None
        city_data = self.db.get_city_by_id(city_id)
        city_lat = city_data.get('lat', 11.0)
        city_lng = city_data.get('lng', 77.0)
        
        if not hotels:
            hub_name = city_data.get('parent_hub')
            if hub_name:
                hub_city = self.db.get_city_by_name(hub_name)
                if hub_city:
                    hotels = self.db.get_hotels(hub_city['city_id'])
                    location_name = hub_city['name']
                    city_lat = hub_city.get('lat', city_lat)
                    city_lng = hub_city.get('lng', city_lng)
        
        if not hotels: return None
        
        rem = usable_budget - transport_cost - (400 * nights * travellers)
        max_p_n = (rem / nights) if rem > 0 else 1000
        
        if max_p_n > 5000: target = [h for h in hotels if h.get('rating', 0) >= 4]
        elif max_p_n > 2500: target = [h for h in hotels if h.get('rating', 0) >= 3]
        else: target = sorted(hotels, key=lambda x: x.get('price_per_night', 9999))[:3]
        
        if not target: target = hotels
        sel = sorted(target, key=lambda x: x.get('price_per_night', 9999))[0]
        
        # Enrich with coords (intensity 0.01 as requested)
        jittered = self._jitter_coords(city_lat, city_lng, 0.01)
        sel['coords'] = {"lat": jittered['lat'], "lng": jittered['lng']}
        
        if location_name:
            sel = sel.copy()
            sel['display_location'] = location_name
            
        return sel

    def generate_itinerary(self, days: int, city_id: int, hotel: Dict[str, Any], num_rooms: int, num_travellers: int, mood: str = "Relaxation") -> List[Dict[str, Any]]:
        city_data = self.db.get_city_by_id(city_id)
        city_lat = city_data.get('lat', 11.0)
        city_lng = city_data.get('lng', 77.0)

        local_pool = self.db.get_attractions(city_id)
        pool = local_pool.copy()
        
        if len(pool) < days:
            hub_name = city_data.get('parent_hub')
            if hub_name:
                hub_city = self.db.get_city_by_name(hub_name)
                if hub_city:
                    hub_pool = self.db.get_attractions(hub_city['city_id'])
                    existing_names = {a['name'] for a in pool}
                    for a in hub_pool:
                        if a['name'] not in existing_names:
                            pool.append(a)
                    
        if not pool:
            pool = [{"name": "Scenic Exploration", "description": "Take a moment to enjoy the local surroundings.", "area": "Local Area"}]

        food_list = self.db.get_food_places(city_id)
        if not food_list:
            food_list = [{"name": "Local Restaurant", "cuisine": "Local", "area": "Nearby"}]

        if mood.lower() == 'adventure': pool.sort(key=lambda x: x.get('outdoor', False), reverse=True)
        else: pool.sort(key=lambda x: x.get('outdoor', True))
            
        itinerary = []
        hotel_name = hotel['name']
        
        for i in range(days):
            spot = pool[i % len(pool)]
            highlight = spot['name']
            jittered = self._jitter_coords(city_lat, city_lng, 0.01)
            spot['coords'] = {"lat": jittered['lat'], "lng": jittered['lng']}
            
            res = food_list[i % len(food_list)]
            res_jittered = self._jitter_coords(city_lat, city_lng, 0.01)
            res['coords'] = {"lat": res_jittered['lat'], "lng": res_jittered['lng']}

            meal_desc = f"Lunch/Dinner at {res['name']} ({res['cuisine']}) in {res.get('area', 'Local Area')}."
            
            if i == 0: stay_desc = f"Check-in and relax at {hotel_name}."
            elif i == 1: stay_desc = f"Enjoy breakfast and morning views at {hotel_name}."
            else: stay_desc = f"Evening leisure at {hotel_name}."
            
            itinerary.append({
                "day": i + 1,
                "activities_list": highlight,
                "daily_activity": highlight,
                "activities": [spot],
                "coords": spot['coords'],
                "stay": stay_desc,
                "meal": meal_desc,
                "restaurant": res
            })
        return itinerary

    def validate_and_correct(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        2. BUDGET VALIDATOR & SELF-CORRECTION LOOP
        - If Total > Budget: Downgrade Hotel -> Transport -> Attractions.
        - 3. 90% MAXIMIZER RULE: If Total < 85% Budget: Upgrade Hotel -> Transport.
        """
        budget = state['budget']
        usable_budget = budget * 0.9 # Buffer
        spent = state['costs']['total']
        city_id = state['city_id']
        
        # DOWN-STEP LOOP
        iteration = 0
        while spent > usable_budget and iteration < 5:
            iteration += 1
            changed = False
            
            # 1. Downgrade Hotel
            hotels = self.db.get_hotels(city_id)
            if hotels:
                cheaper = [h for h in hotels if h.get('price_per_night', 9999) < state['selected_hotel'].get('price_per_night', 9999)]
                if cheaper:
                    cheaper.sort(key=lambda x: x.get('price_per_night', 9999), reverse=True)
                    target = cheaper[0]
                    rooms = (state['travellers'] + (target.get('max_people', 2) or 2) - 1) // (target.get('max_people', 2) or 2)
                    new_h_c = target.get('price_per_night', 0) * rooms * state['days']
                    state['selected_hotel'] = target
                    state['costs']['hotel'] = new_h_c
                    spent = spent - (state['costs']['hotel'] - new_h_c) # Incorrect math fix:
                    state['costs']['total'] = sum([state['costs'][k] for k in state['costs'] if k != 'total'])
                    spent = state['costs']['total']
                    changed = True
            
            # 2. Downgrade Transport (Private -> Bus)
            if not changed and state['selected_transport'].get('mode', '').lower() != 'bus':
                routes = self.db.get_transport(state['origin'], state['destination'])
                if routes:
                    buses = [o for o in routes[0].get('options', []) if 'bus' in o.get('mode','').lower()]
                    if buses:
                        bus = sorted(buses, key=lambda x: x.get('cost', 9999))[0]
                        new_t_c = (bus.get('cost', 500) * state['travellers']) * 2
                        state['selected_transport'].update(bus)
                        state['costs']['transport'] = new_t_c
                        state['costs']['total'] = sum([state['costs'][k] for k in state['costs'] if k != 'total'])
                        spent = state['costs']['total']
                        changed = True
            
            if not changed: break

        # 3. 90% MAXIMIZER RULE
        iteration = 0
        while spent < (usable_budget * 0.85) and iteration < 5:
            iteration += 1
            changed = False
            
            # 1. Upgrade Hotel
            hotels = self.db.get_hotels(city_id)
            if hotels:
                better = [h for h in hotels if h.get('price_per_night', 0) > state['selected_hotel'].get('price_per_night', 0)]
                if better:
                    better.sort(key=lambda x: x.get('price_per_night', 0))
                    for bh in better:
                        r = (state['travellers'] + (bh.get('max_people', 2) or 2) - 1) // (bh.get('max_people', 2) or 2)
                        new_h_c = bh.get('price_per_night', 0) * r * state['days']
                        pot_total = spent - state['costs']['hotel'] + new_h_c
                        if pot_total <= usable_budget:
                            state['selected_hotel'] = bh
                            state['costs']['hotel'] = new_h_c
                            state['costs']['total'] = pot_total
                            spent = pot_total
                            changed = True
                            break
            
            # 2. Upgrade Transport
            if not changed and state['selected_transport'].get('mode', '').lower() == 'bus':
                routes = self.db.get_transport(state['origin'], state['destination'])
                if routes:
                    cabs = [o for o in routes[0].get('options', []) if 'cab' in o.get('type','').lower() or 'sedan' in o.get('type','').lower()]
                    if cabs:
                        cab = sorted(cabs, key=lambda x: x.get('cost', 9999))[0]
                        new_t_c = (cab.get('cost', 500) * state['travellers']) * 2
                        pot_total = spent - state['costs']['transport'] + new_t_c
                        if pot_total <= usable_budget:
                            state['selected_transport'].update(cab)
                            state['costs']['transport'] = new_t_c
                            state['costs']['total'] = pot_total
                            spent = pot_total
                            changed = True
            
            if not changed: break
            
        return state