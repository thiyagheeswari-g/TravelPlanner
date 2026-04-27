import json

def append_entry(file_path, key, entry):
    with open(file_path, 'r') as f:
        data = json.load(f)
    data[key].append(entry)
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)

# Add Hoysala Stay
append_entry(r'c:\Users\THIYAGHEESWARI G\Desktop\TravelPlanner\dataset\hotels.json', 'hotels', {
    "hotel_id": 101,
    "city_id": 18,
    "name": "Hoysala Stay",
    "price_per_night": 1200,
    "max_people": 2,
    "area": "Hampi Bazaar",
    "hotel_type": "budget",
    "rating": 4.2
})

# Add Mango Tree
append_entry(r'c:\Users\THIYAGHEESWARI G\Desktop\TravelPlanner\dataset\food_places.json', 'food_places', {
    "food_id": 101,
    "city_id": 18,
    "name": "Mango Tree",
    "cuisine": "South Indian",
    "avg_cost": 350,
    "suitable_for": ["family", "friends", "couple", "solo"],
    "area": "Hampi Bazaar"
})

print("Successfully added test data.")
