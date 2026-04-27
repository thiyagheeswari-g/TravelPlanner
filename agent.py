import json
import os
import re
from typing import List, Dict, Any, Optional, Annotated
from typing_extensions import TypedDict

from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

from database import DataService
from planner import TravelPlannerLogic

class PlanState(TypedDict):
    query: str
    chat_history: List[Dict[str, str]]
    destination: Optional[str]
    origin: str
    days: int
    budget: float
    travellers: int
    mood: str
    trip_style: str
    travel_month: str
    food_preference: str
    
    # Selected Items
    selected_hotel: Optional[Dict[str, Any]]
    selected_transport: Optional[Dict[str, Any]]
    food_recommendations: List[Dict[str, Any]]
    itinerary_days: List[Dict[str, Any]]
    
    # Internal State
    costs: Dict[str, float]
    status: str
    field_changes: List[str]
    final_response: str
    kpi: Optional[Dict[str, Any]]
    media_cards: Optional[Dict[str, Any]]
    city_id: Optional[int]

class TravelAgent:
    def __init__(self, db: Optional[DataService] = None):
        self.db = db if db else DataService()
        self.logic = TravelPlannerLogic(self.db)
        
        hf_token = os.getenv("HUGGINGFACEHUB_API_TOKEN")
        if hf_token:
            base_llm = HuggingFaceEndpoint(
                repo_id="mistralai/Mistral-7B-Instruct-v0.2",
                huggingfacehub_api_token=hf_token,
                temperature=0.1,
                max_new_tokens=512,
                task="conversational",
                provider="featherless-ai"
            )
            self.llm = ChatHuggingFace(llm=base_llm)
        else:
            self.llm = None
            
        self.workflow = self._build_workflow()

    def _build_workflow(self):
        builder = StateGraph(PlanState)
        builder.add_node("planner", self.planner_node)
        builder.add_node("formatter", self.formatter_node)
        
        builder.set_entry_point("planner")
        builder.add_edge("planner", "formatter")
        builder.add_edge("formatter", END)
        return builder.compile()

    def parse_budget(self, text):
        if not text: return None
        text = str(text).lower().replace(",", "")
        match_k = re.search(r'(\d+)\s*k', text)
        if match_k: return float(match_k.group(1)) * 1000
        match_pref = re.search(r'(?:budget|₹|rs\.?|rate)\s*:?\s*(\d+)', text)
        if match_pref: return float(match_pref.group(1))
        numbers = re.findall(r'\d+', text)
        for n in numbers:
            if float(n) > 500: return float(n)
        return None

    def extract_info(self, query: str, history: List[Dict[str, str]]) -> Dict[str, Any]:
        extracted = {k: None for k in ['destination', 'origin', 'days', 'budget', 'travellers', 'mood']}
        q_low = query.lower()
        
        # Regex Extraction
        cities = [c['name'] for c in self.db._cities]
        for c in cities:
            if c.lower() in q_low: extracted['destination'] = c
            
        days_match = re.search(r'(\d+)\s*(?:days|day|night)', q_low)
        if days_match: extracted['days'] = int(days_match.group(1))
        
        trav_match = re.search(r'(\d+)\s*(?:people|travellers|person|adults)', q_low)
        if trav_match: extracted['travellers'] = int(trav_match.group(1))
        
        extracted['budget'] = self.parse_budget(q_low)
        
        styles = ['luxury', 'budget', 'mid', 'relaxation', 'adventure']
        for s in styles:
            if s in q_low: extracted['mood'] = s.capitalize()
            
        # LLM Extraction (Secondary)
        if self.llm:
            hist_str = "\n".join([f"{m['role']}: {m['content']}" for m in history[-3:]])
            prompt = f"Extract trip details as JSON: '{query}'. History: {hist_str}"
            try:
                resp = self.llm.invoke([HumanMessage(content=prompt)])
                json_match = re.search(r'\{.*\}', resp.content, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                    for k in extracted:
                        if extracted[k] is None: extracted[k] = data.get(k)
            except: pass
        return extracted

    def planner_node(self, state: PlanState) -> PlanState:
        # 1. Validation & City Search
        dest = state['destination']
        city = self.db.get_city_by_name(dest)
        if not city:
            state['status'] = 'missing_dest'
            return state
        state['city_id'] = city['city_id']
        
        # 2. Transport Selection
        origin, dest_name = state['origin'], state['destination']
        tier = 'luxury' if state['budget']/state['travellers']/state['days'] > 5000 else 'mid'
        if state['budget']/state['travellers']/state['days'] < 2500: tier = 'budget'
        
        routes = self.db.get_transport(origin, dest_name)
        if routes:
            opts = routes[0].get('options', [])
            targets = {'luxury': ['Cab', '1AC'], 'mid': ['2AC', 'AC Bus'], 'budget': ['Sleeper', 'Bus']}[tier]
            filtered = [o for o in opts if any(t.lower() in o.get('type','').lower() or t.lower() in o.get('mode','').lower() for t in targets)]
            if not filtered: filtered = opts
            filtered.sort(key=lambda x: x.get('cost', 9999))
            sel = filtered[-1] if tier == 'luxury' else filtered[0]
            state['selected_transport'] = {**sel, "from_station": routes[0].get('from_station', origin), "to_station": routes[0].get('to_station', dest_name)}
        else:
            # Proxy Fallback
            o_city = self.db.get_city_by_name(origin)
            cost = self.logic.calculate_proxy_transport_cost([o_city['lat'], o_city['lng']] if o_city else None, [city['lat'], city['lng']], tier)
            state['selected_transport'] = {"mode": "Cab" if tier == "luxury" else "Bus", "provider": "Regional Carrier", "total_estimated_cost": cost, "from_station": origin, "to_station": dest_name, "departure_time": "Flexible", "train_name": "Regional Express"}

        # 3. Hotel Selection
        hotels = self.db.get_hotels(city['city_id'])
        h_sel = self.logic.select_hotel_best_fit(city['city_id'], state['travellers'], state['budget'], state['days'], state['selected_transport']['total_estimated_cost'])
        if not h_sel: h_sel = sorted(hotels, key=lambda x: x.get('price_per_night', 9999))[0]
        state['selected_hotel'] = h_sel

        # 4. Itinerary & Costs
        max_p = h_sel.get('max_people', 2) or 2
        rooms = (state['travellers'] + max_p - 1) // max_p
        attractions = self.db.get_attractions(city['city_id'])
        state['itinerary_days'] = self.logic.generate_itinerary(state['days'], attractions, h_sel, rooms, state['travellers'], state['mood'])
        
        t_cost = (state['selected_transport'].get('total_estimated_cost', 500) * state['travellers']) * 2
        h_cost = h_sel.get('price_per_night', 0) * rooms * state['days']
        f_cost = 400 * state['days'] * state['travellers']
        a_cost = sum(sum(act.get('cost', 50) for act in d['activities']) for d in state['itinerary_days']) * state['travellers']
        
        total = t_cost + h_cost + f_cost + a_cost
        
        # Anti-Crash Safety Valve
        if total > state['budget']:
            h_sel = sorted(hotels, key=lambda x: x.get('price_per_night', 0))[0]
            state['selected_hotel'] = h_sel
            h_cost = h_sel.get('price_per_night', 0) * rooms * state['days']
            total = t_cost + h_cost + f_cost + a_cost
            state['explanation'] = "Optimized to fit budget."

        state['costs'] = {"transport": t_cost, "hotel": h_cost, "food": f_cost, "activities": a_cost, "total": total}
        state['status'] = 'done'
        return state

    def formatter_node(self, state: PlanState) -> PlanState:
        if state['status'] == 'missing_dest':
            state['final_response'] = "Which destination are you planning for? (e.g., Ooty, Munnar)"
            return state
            
        t = state['selected_transport']
        h = state['selected_hotel']
        summary = f"Got it! Your {state['days']}-day {state['destination']} trip for {state['travellers']}. "
        if state['field_changes']: summary = f"Updated! Adjusted for {', '.join(state['field_changes'])}. "
        
        summary += f"\nLogistics: Board {t.get('train_name', t.get('mode'))} from {t.get('from_station')} | Dep: {t.get('departure_time')}\n"
        summary += f"Stay: {h['name']} ({h['rating']}★) | Total: ₹{state['costs']['total']:,}"
        
        state['final_response'] = summary
        state['kpi'] = {"total_budget": state['budget'], "spent": state['costs']['total'], "remaining": state['budget'] - state['costs']['total']}
        state['media_cards'] = {"stays": [h], "restaurants": self.db.get_food_places(state['city_id'])[:4]}
        return state

    def run(self, input_data: Dict[str, Any]):
        query = input_data.get("query", "")
        history = input_data.get("chat_history") or []
        ext = self.extract_info(query, history)
        
        state: PlanState = {
            "query": query, "chat_history": history,
            "destination": ext.get('destination') or input_data.get('destination'),
            "origin": ext.get('origin') or input_data.get('origin') or "Chennai",
            "days": int(ext.get('days') or input_data.get('days') or 3),
            "budget": float(ext.get('budget') or input_data.get('budget') or 20000),
            "travellers": int(ext.get('travellers') or input_data.get('travellers') or 2),
            "mood": ext.get('mood') or input_data.get('mood') or "Relaxation",
            "travel_month": "May", "food_preference": "Both", "field_changes": [],
            "selected_hotel": None, "selected_transport": None, "itinerary_days": [], "food_recommendations": []
        }
        for f in ['days', 'travellers', 'budget', 'destination', 'mood']:
            if input_data.get(f) and ext.get(f) and str(input_data[f]) != str(ext[f]): state['field_changes'].append(f)
        return self.workflow.invoke(state)