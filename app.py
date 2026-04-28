from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from agent import TravelAgent
from database import DataService
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import uvicorn
import uvicorn

app = FastAPI(title="TravelPlanner API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = DataService()
agent = TravelAgent(db)

class TripRequest(BaseModel):
    query: str
    chat_history: Optional[List[Dict[str, Any]]] = []
    destination: Optional[str] = None
    origin: Optional[str] = None
    days: Optional[int] = None
    budget: Optional[float] = None
    travel_month: Optional[str] = None
    trip_type: Optional[str] = None
    travellers: Optional[int] = 2
    food_preference: Optional[str] = None
    weather_preference: Optional[str] = None
    travel_mood: Optional[str] = None
    from_state: Optional[str] = None
    from_hub: Optional[str] = None
    to_state: Optional[str] = None
    travel_month_mode: Optional[str] = None

@app.post("/plan")
async def plan_trip(request: TripRequest):
    try:
        result = agent.run(request.model_dump())
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cities")
async def get_all_cities():
    return db.get_all_cities()

@app.get("/cities/{state_name}")
async def get_cities(state_name: str):
    return db.get_cities_by_state(state_name)

@app.get("/hubs/{state_name}")
async def get_hubs(state_name: str):
    return db.get_hubs_by_state(state_name)

@app.get("/moods")
async def get_moods():
    return {
        "travel_moods": db.get_travel_moods(),
        "city_mood_mapping": db.get_city_mood_mapping()
    }

class SessionData(BaseModel):
    session_id: str
    title: str
    messages: List[Dict[str, Any]]
    plan_metadata: Dict[str, Any]

@app.post("/sessions")
async def save_session(data: SessionData):
    # Auto-Title Generation Logic
    title = data.title
    if not title or title.strip() == "" or title == "New Journey":
        if data.plan_metadata and data.plan_metadata.get('destination'):
            title = f"Journey to {data.plan_metadata['destination']}"
        elif data.messages:
            user_msgs = [m for m in data.messages if m.get('role') == 'user']
            if user_msgs:
                first_msg = user_msgs[0]['content']
                title = first_msg[:30] + "..." if len(first_msg) > 30 else first_msg
            else:
                title = "Travel Discussion"
        else:
            title = "New Journey"

    db.save_session(data.session_id, title, data.messages, data.plan_metadata)
    return {"status": "success", "session_title": title}

@app.get("/sessions")
async def get_sessions():
    return db.get_all_sessions()

@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    db.delete_session(session_id)
    return {"status": "success"}

@app.get("/")
async def root():
    return {"message": "TravelPlanner API is running"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)