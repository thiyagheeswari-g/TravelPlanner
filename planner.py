import math
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

    def select_hotel_best_fit(self, city_id: int, travellers: int, total_budget: float, nights: int, transport_cost: float = 0) -> Optional[Dict[str, Any]]:
        hotels = self.db.get_hotels(city_id)
        location_name = None
        
        if not hotels:
            city_data = self.db.get_city_by_id(city_id)
            hub_name = city_data.get('parent_hub')
            if hub_name:
                hub_city = self.db.get_city_by_name(hub_name)
                if hub_city:
                    hotels = self.db.get_hotels(hub_city['city_id'])
                    location_name = hub_city['name']
        
        if not hotels: return None
        
        rem = total_budget - transport_cost - (400 * nights * travellers)
        max_p_n = (rem / nights) if rem > 0 else 1000
        
        if max_p_n > 5000: target = [h for h in hotels if h.get('rating', 0) >= 4]
        elif max_p_n > 2500: target = [h for h in hotels if h.get('rating', 0) >= 3]
        else: target = sorted(hotels, key=lambda x: x.get('price_per_night', 9999))[:3]
        
        if not target: target = hotels
        sel = sorted(target, key=lambda x: x.get('price_per_night', 9999))[0]
        
        if location_name:
            sel = sel.copy()
            sel['display_location'] = location_name
            
        return sel

    def generate_itinerary(self, days: int, city_id: int, hotel: Dict[str, Any], num_rooms: int, num_travellers: int, mood: str = "Relaxation") -> List[Dict[str, Any]]:
        """
        STEP 4: BORROW & STRETCH
        - One-Spot Rule: Only one unique attraction per day.
        - Hub Borrowing: Pull from parent_hub if local exhausted.
        """
        local_pool = self.db.get_attractions(city_id)
        pool = local_pool.copy()
        
        # Linear Hub Borrowing
        if len(pool) < days:
            city_data = self.db.get_city_by_id(city_id)
            hub_name = city_data.get('parent_hub')
            if hub_name:
                hub_city = self.db.get_city_by_name(hub_name)
                if hub_city:
                    hub_pool = self.db.get_attractions(hub_city['city_id'])
                    pool.extend(hub_pool)
                    
        if not pool:
            pool = [{"name": "Scenic Exploration", "description": "Take a moment to enjoy the local surroundings.", "area": "Local Area"}]

        if mood.lower() == 'adventure': pool.sort(key=lambda x: x.get('outdoor', False), reverse=True)
        else: pool.sort(key=lambda x: x.get('outdoor', True))
            
        itinerary = []
        for i in range(days):
            # One-Spot Rule: ensures we pick exactly one unique spot
            spot = pool[i % len(pool)]
            
            # Format as single string for "Sightseeing Highlight"
            highlight = f"{spot['name']}: {spot.get('description', 'Sightseeing')}"
            
            itinerary.append({
                "day": i + 1,
                "activities_list": highlight,
                "activities": [spot],
                "stay": f"Staying at {hotel['name']} in {hotel.get('display_location', 'Local Area')}",
                "meal": "Recommended: Local Specialty"
            })
        return itinerary

    def maximize_budget(self, state: Dict[str, Any]) -> Dict[str, Any]:
        budget = state['budget']
        spent = state['costs']['total']
        city_id = state['city_id']
        
        iteration = 0
        while spent < (budget * 0.9) and iteration < 5:
            iteration += 1
            changed = False
            
            # 1. Upgrade Hotel
            hotels = self.db.get_hotels(city_id)
            if not hotels: 
                city_data = self.db.get_city_by_id(city_id)
                hub_name = city_data.get('parent_hub')
                if hub_name:
                    hub_city = self.db.get_city_by_name(hub_name)
                    if hub_city: hotels = self.db.get_hotels(hub_city['city_id'])
            
            if hotels:
                better = [h for h in hotels if h.get('price_per_night', 0) > state['selected_hotel'].get('price_per_night', 0)]
                if better:
                    better.sort(key=lambda x: x.get('price_per_night', 0))
                    for bh in better:
                        r = (state['travellers'] + (bh.get('max_people', 2) or 2) - 1) // (bh.get('max_people', 2) or 2)
                        new_h_c = bh.get('price_per_night', 0) * r * state['days']
                        pot_total = spent - state['costs']['hotel'] + new_h_c
                        if pot_total <= budget:
                            state['selected_hotel'] = bh
                            state['costs']['hotel'] = new_h_c
                            state['costs']['total'] = pot_total
                            spent = pot_total
                            changed = True
                            break
            
            # 2. Upgrade Transport
            if state['selected_transport'].get('mode', '').lower() == 'bus':
                routes = self.db.get_transport(state['origin'], state['destination'])
                if routes:
                    cabs = [o for o in routes[0].get('options', []) if 'cab' in o.get('type','').lower() or 'sedan' in o.get('type','').lower()]
                    if cabs:
                        cab = sorted(cabs, key=lambda x: x.get('cost', 9999))[0]
                        new_t_c = (cab.get('cost', 500) * state['travellers']) * 2
                        pot_total = spent - state['costs']['transport'] + new_t_c
                        if pot_total <= budget:
                            state['selected_transport'].update(cab)
                            state['costs']['transport'] = new_t_c
                            state['costs']['total'] = pot_total
                            spent = pot_total
                            changed = True
            
            if not changed: break
            
        return state