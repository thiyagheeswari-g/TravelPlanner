import sys
import os
import math

# Add the project directory to sys.path
sys.path.append(r"c:\Users\THIYAGHEESWARI G\Desktop\TravelPlanner")

from agent import TravelAgent
from database import DataService

def test_budget_logic():
    db = DataService()
    agent = TravelAgent(db)
    
    # Scenario: Hampi, 5 People, 3 Days, Budget 50,000
    # Expected: 
    # 1. Hotel selection must stay under 30,000 (60% of 50k)
    # 2. Transport cost: (750 * 5) * 2 = 7,500
    # 3. Rooms: ceil(5/2) = 3 rooms
    
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
    
    print("Running Budget Logic Test...")
    try:
        result = agent.run(input_data)
        print("Status:", result['status'])
        print("Selected Hotel:", result['selected_hotel']['name'])
        print("Hotel Tier:", result['budget_tier'])
        print("Hotel Price/Night:", result['selected_hotel']['price_per_night'])
        
        num_travellers = 5
        nights = 3
        max_p = result['selected_hotel']['max_people']
        num_rooms = math.ceil(num_travellers / max_p)
        h_total = result['selected_hotel']['price_per_night'] * num_rooms * nights
        
        print(f"Calculated Hotel Total: {h_total} (Cap: 30000)")
        if h_total <= 30000:
            print("SUCCESS: Hotel budget cap respected.")
        else:
            print("FAILURE: Hotel budget cap exceeded!")
            
        print("Transport Cost (Total):", result['costs']['transport'])
        # (750 * 5) * 2 = 7500
        if result['costs']['transport'] == 7500:
            print("SUCCESS: Transport round-trip math correct.")
        else:
            print(f"FAILURE: Transport math mismatch! Expected 7500, got {result['costs']['transport']}")
            
        print("Total Cost:", result['costs']['total'])
        
    except Exception as e:
        print("ERROR during execution:", e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_budget_logic()
