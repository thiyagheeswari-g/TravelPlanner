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
    origin: Optional[str]
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
    available_transport: List[Dict[str, Any]]
    transport_meta: Optional[Dict[str, Any]]
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
    explanation: str

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
        builder.add_node("check_missing", self.check_missing_node)
        builder.add_node("planner", self.planner_node)
        builder.add_node("formatter", self.formatter_node)
        
        builder.set_entry_point("check_missing")
        builder.add_conditional_edges(
            "check_missing",
            self.should_continue,
            {
                "continue": "planner",
                "ask": "formatter",
                "greet": "formatter"
            }
        )
        builder.add_edge("planner", "formatter")
        builder.add_edge("formatter", END)
        return builder.compile()

    def should_continue(self, state: PlanState) -> str:
        if state['status'] == 'greeting': return "greet"
        if state['status'] == 'gathering': return "ask"
        return "continue"

    def check_missing_node(self, state: PlanState) -> PlanState:
        # 2. GREETING FIX: Bypass checks for simple greetings
        greetings = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening"]
        q_clean = state['query'].lower().strip().replace("!", "").replace(".", "").replace("?", "")
        if q_clean in greetings:
            state['status'] = 'greeting'
            state['final_response'] = "Hello! I'm Antigravity AI. Where are we heading today? I can help with transport, hotels, and a unique daily plan."
            return state

        if not state.get('destination'):
            state['status'] = 'gathering'
            state['final_response'] = "I'd love to plan a trip for you! Which destination are you thinking of? (e.g., Ooty, Chennai)"
            return state
            
        if not state.get('origin'):
            state['status'] = 'gathering'
            state['final_response'] = f"I'd love to plan your trip to {state['destination']}! To find the best transport options, could you tell me where you'll be departing from?"
            return state
            
        state['status'] = 'ready'
        return state

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
        
        cities = [c['name'] for c in self.db._cities]
        for c in cities:
            if c.lower() in q_low:
                if f"from {c.lower()}" in q_low: extracted['origin'] = c
                elif f"to {c.lower()}" in q_low or "trip to" in q_low: extracted['destination'] = c
                else:
                    if not extracted['destination']: extracted['destination'] = c
            
        days_match = re.search(r'(\d+)\s*(?:days|day|night)', q_low)
        if days_match: extracted['days'] = int(days_match.group(1))
        
        trav_match = re.search(r'(\d+)\s*(?:people|travellers|person|adults|members)', q_low)
        if trav_match: extracted['travellers'] = int(trav_match.group(1))
        
        extracted['budget'] = self.parse_budget(q_low)
        
        styles = ['luxury', 'budget', 'mid', 'relaxation', 'adventure']
        for s in styles:
            if s in q_low: extracted['mood'] = s.capitalize()
            
        return extracted

    def planner_node(self, state: PlanState) -> PlanState:
        city = self.db.get_city_by_name(state['destination'])
        if not city:
            state['status'] = 'gathering'
            state['final_response'] = f"I couldn't find {state['destination']} in my database."
            return state
        state['city_id'] = city['city_id']
        
        routes = self.db.get_transport(state['origin'], state['destination'])
        if routes:
            opts = routes[0].get('options', [])
            state['transport_meta'] = {
                "from_city": routes[0].get('from_city'),
                "from_station": routes[0].get('from_station'),
                "to_city": routes[0].get('to_city'),
                "to_station": routes[0].get('to_station'),
                "distance_km": routes[0].get('distance_km'),
                "distance_category": routes[0].get('distance_category'),
                "area": routes[0].get('area')
            }
            state['available_transport'] = opts
            
            per_person_day = state['budget'] / (state['travellers'] * state['days'])
            tier = 'luxury' if per_person_day > 5000 else ('mid' if per_person_day > 2500 else 'budget')
            
            targets = {
                'luxury': ["Cab", "Sedan", "1AC", "First Class"],
                'mid': ["2AC", "3AC", "AC Deluxe", "Sleeper"],
                'budget': ["Non-AC", "Unreserved", "General Bus", "Sleeper"]
            }[tier]
            
            filtered = [o for o in opts if any(t.lower() in (o.get('type','') + o.get('mode','')).lower() for t in targets)]
            if not filtered: filtered = opts
            filtered.sort(key=lambda x: x.get('cost', 9999))
            sel = filtered[-1] if tier == 'luxury' else filtered[0]
            state['selected_transport'] = {**sel, **state['transport_meta']}
        else:
            o_city = self.db.get_city_by_name(state['origin'])
            cost = self.logic.calculate_proxy_transport_cost([o_city['lat'], o_city['lng']] if o_city else None, [city['lat'], city['lng']], 'mid')
            state['transport_meta'] = {"from_city": state['origin'], "to_city": state['destination'], "from_station": state['origin'], "to_station": state['destination'], "distance_km": 0, "area": "Custom Route"}
            state['selected_transport'] = {"mode": "Cab", "provider": "Private", "cost": cost, "type": "Private", "train_name": "N/A", "departure_time": "Flexible", **state['transport_meta']}
            state['available_transport'] = [state['selected_transport']]

        h_sel = self.logic.select_hotel_best_fit(city['city_id'], state['travellers'], state['budget'], state['days'], state['selected_transport'].get('cost', 500))
        if not h_sel: h_sel = self.db.get_hotels(city['city_id'])[0]
        state['selected_hotel'] = h_sel
        
        rooms = (state['travellers'] + (h_sel.get('max_people', 2) or 2) - 1) // (h_sel.get('max_people', 2) or 2)
        state['itinerary_days'] = self.logic.generate_itinerary(state['days'], city['city_id'], h_sel, rooms, state['travellers'], state['mood'])
        
        t_c = (state['selected_transport'].get('cost', 500) * state['travellers']) * 2
        h_c = h_sel.get('price_per_night', 0) * rooms * state['days']
        f_c = 400 * state['days'] * state['travellers']
        a_c = sum(sum(act.get('cost', 50) for act in d['activities']) for d in state['itinerary_days']) * state['travellers']
        state['costs'] = {"transport": t_c, "hotel": h_c, "food": f_c, "activities": a_c, "total": t_c + h_c + f_c + a_c}
        
        state = self.logic.maximize_budget(state)
        state['status'] = 'done'
        return state

    def formatter_node(self, state: PlanState) -> PlanState:
        if state['status'] in ['gathering', 'greeting']: return state
        state['final_response'] = f"I've planned your {state['days']}-day trip to {state['destination']}! Check the dashboard for the full plan."
        state['kpi'] = {"total_budget": state['budget'], "spent": state['costs']['total'], "remaining": state['budget'] - state['costs']['total']}
        state['media_cards'] = {"stays": [state['selected_hotel']], "restaurants": self.db.get_food_places(state['city_id'])[:4]}
        return state

    def run(self, input_data: Dict[str, Any]):
        query = input_data.get("query", "")
        history = input_data.get("chat_history") or []
        ext = self.extract_info(query, history)
        
        destination = ext.get('destination') or input_data.get('destination')
        origin = ext.get('origin') or input_data.get('origin')
        
        # 4. BUDGET CONTEXT RESET RULE
        # If destination changes, reset budget to ₹50k (Initial Input)
        prev_dest = input_data.get('destination')
        if prev_dest and destination and prev_dest != destination:
            budget = 50000.0
        else:
            budget = ext.get('budget') or input_data.get('budget') or 50000.0

        state: PlanState = {
            "query": query, "chat_history": history,
            "destination": destination,
            "origin": origin,
            "days": int(ext.get('days') or input_data.get('days') or 3),
            "budget": float(budget),
            "travellers": int(ext.get('travellers') or input_data.get('travellers') or 2),
            "mood": ext.get('mood') or input_data.get('mood') or "Relaxation",
            "travel_month": "May", "food_preference": "Both", "field_changes": [],
            "selected_hotel": None, "selected_transport": None, "available_transport": [], "transport_meta": None,
            "itinerary_days": [], "food_recommendations": []
        }
        return self.workflow.invoke(state)