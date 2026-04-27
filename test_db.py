from database import DataService
import json

try:
    print("Initializing DataService...")
    db = DataService()
    print("DataService initialized successfully.")
    cities = db.get_all_cities()
    print(f"Loaded {len(cities)} cities.")
    
    # Test transport
    routes = db.get_transport("Chennai", "Hampi")
    print(f"Found {len(routes)} routes from Chennai to Hampi.")
    if routes:
        print(f"First route: {routes[0]['route_id']}")
        print(f"To Station Area: {routes[0].get('to_station_area')}")

    # Test attractions
    attrs = db.get_attractions(18) # Hampi is city_id 18
    print(f"Found {len(attrs)} attractions in Hampi.")
    if attrs:
        print(f"First attraction: {attrs[0]['name']} in {attrs[0]['area']}")

except Exception as e:
    print(f"Error: {e}")
