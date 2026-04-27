import sys
import os

# Add the project directory to sys.path
sys.path.append(r"c:\Users\THIYAGHEESWARI G\Desktop\TravelPlanner")

from agent import TravelAgent
from database import DataService

def test_hampi():
    db = DataService()
    agent = TravelAgent(db)
    
    input_data = {
        "query": "Plan a trip to Hampi for 5 people with Cultural mood",
        "destination": "Hampi",
        "origin": "Chennai",
        "days": 3,
        "budget": 50000,
        "travel_month": "October",
        "trip_type": "family",
        "travellers": 5,
        "food_preference": "Both"
    }
    
    print("Running Hampi Test...")
    try:
        result = agent.run(input_data)
        print("Status:", result['status'])
        print("Destination:", result['destination'])
        print("Final Response Summary:", result['final_response'][:200].replace('₹', 'Rs.'))
        print("Hotel:", result['selected_hotel']['name'])
        print("Rooms:", result['itinerary_days'][0]['stay'].replace('₹', 'Rs.'))
        print("Transport:", result['selected_transport']['train_name'])
        
        # Check for Virupaksha Temple
        attractions = [a['name'] for day in result['itinerary_days'] for a in day.get('activities', [])]
        print("Attractions found:", attractions)
        if "Virupaksha Temple" in attractions:
            print("SUCCESS: Virupaksha Temple found.")
        else:
            print("FAILURE: Virupaksha Temple not found in itinerary.")
            
        # Check budget breakdown
        print("Costs:", result['costs'])
        
    except Exception as e:
        print("ERROR during execution:", e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_hampi()
