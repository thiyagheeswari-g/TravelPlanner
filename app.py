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
    destination: Optional[str] = None
    origin: Optional[str] = None
    days: Optional[int] = None
    budget: Optional[float] = None
    travel_month: Optional[str] = None
    trip_type: Optional[str] = None
    travellers: Optional[int] = 1
    food_preference: Optional[str] = None
    weather_preference: Optional[str] = None

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

@app.get("/weather")
async def get_live_weather(city: str):
    api_key = os.getenv("OPENWEATHER_API_KEY", "b6907d289e10d714a6e88b30761fae22") # fallback key for testing
    if not api_key:
        return {"temp": 25, "condition": "Clear Sky", "icon": "01d"}
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city},in&appid={api_key}&units=metric"
        resp = requests.get(url)
        data = resp.json()
        if resp.status_code == 200:
            return {
                "temp": round(data["main"]["temp"]),
                "condition": data["weather"][0]["main"],
                "icon": data["weather"][0]["icon"]
            }
        return {"temp": 24, "condition": "Clear", "icon": "01d"}
    except Exception:
        return {"temp": 24, "condition": "Clear", "icon": "01d"}

@app.get("/")
async def root():
    return {"message": "TravelPlanner API is running"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
