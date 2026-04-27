from typing import List, Dict, Any, Optional

class TravelPlannerLogic:
    def __init__(self, data_service):
        self.db = data_service

    def score_months(self, weather_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Scores months based on:
        - temperature_type (pleasant > cool > hot)
        - rainy (false is better)
        """
        scored = []
        for w in weather_list:
            score = 0
            temp_type = w.get('temperature_type', 'pleasant').lower()
            is_rainy = w.get('rainy', False)
            
            # Temperature Score
            if temp_type == 'pleasant':
                score += 50
            elif temp_type == 'cool':
                score += 30
            elif temp_type == 'hot':
                score += 10
            else:
                score += 20 # moderate/unknown
                
            # Rainfall Score
            if not is_rainy:
                score += 50
            else:
                score += 10
            
            scored.append({**w, "weather_score": score})
            
        # Sort by score descending
        return sorted(scored, key=lambda x: x['weather_score'], reverse=True)


    def filter_attractions(self, attractions: List[Dict[str, Any]], weather: Dict[str, Any], preferences: Dict[str, Any]) -> List[Dict[str, Any]]:
        is_rainy = weather.get('condition', '').lower() in ['rainy', 'heavy rain', 'monsoon']
        filtered = []
        for attr in attractions:
            # Strictly exclude outdoor if rainy
            if is_rainy and attr.get('type') == 'Outdoor':
                continue
            filtered.append(attr)
            
        # If the list is empty (e.g. only outdoor activities exists and it's rainy), 
        # we might want to return some anyway but warn the user, or find indoor alternatives.
        # For now, we return what matches.
        return filtered

    def select_hotel(self, city_id: int, travellers: int, budget: float, trip_type: str) -> Optional[Dict[str, Any]]:
        hotels = self.db.get_hotels(city_id)
        if not hotels: return None
        
        if trip_type == 'solo':
            hotels.sort(key=lambda x: x.get('price_per_night', 99999))
        elif trip_type == 'couple':
            hotels.sort(key=lambda x: x.get('rating', 0), reverse=True)
        else:
            hotels.sort(key=lambda x: x.get('price_per_night', 99999))

        return hotels[0] if hotels else None

    def group_activities_by_area(self, attractions: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        areas = {}
        for attr in attractions:
            area = attr.get('area', 'General')
            if area not in areas:
                areas[area] = []
            areas[area].append(attr)
        return areas
