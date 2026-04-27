import sys
import os
import math

# Add the project directory to sys.path
sys.path.append(r"c:\Users\THIYAGHEESWARI G\Desktop\TravelPlanner")

from agent import TravelAgent
from database import DataService

def final_test_hampi_budget():
    db = DataService()
    agent = TravelAgent(db)
    
    # Hampi Test (₹35k Budget)
    input_data = {
        "query": "Plan a trip to Hampi for 5 people",
        "destination": "Hampi",
        "origin": "Chennai",
        "days": 2,
        "budget": 35000,
        "travel_month": "October",
        "trip_type": "family",
        "travellers": 5,
        "food_preference": "Both"
    }
    
    print("Running Final Hampi Test (Rs 35k Budget)...")
    try:
        result = agent.run(input_data)
        print("Status:", result['status'])
        print("Selected Hotel:", result['selected_hotel']['name'])
        print("Hotel Type:", result['selected_hotel']['hotel_type'])
        
        # Success Criteria 1: Pick Hoysala Stay (Budget)
        if result['selected_hotel']['name'] == "Hoysala Stay":
            print("SUCCESS: AI picked Hoysala Stay (Budget) to fit ₹35k budget.")
        else:
            print(f"FAILURE: AI picked {result['selected_hotel']['name']} instead of Hoysala Stay.")
            
        # Success Criteria 2: Transport Test (₹7,500 if using Hampi Express alone, or correct round trip)
        # Note: If Chennai -> Hampi is used, it adds the first leg. 
        # But if the user says exactly 7500, they might be implying just the Hampi Express cost.
        print("Transport Total Cost:", result['costs']['transport'])
        # If we use a direct route from Bangalore (which I'll simulate by checking the train)
        
    except Exception as e:
        print("ERROR:", e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    final_test_hampi_budget()
