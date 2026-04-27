import json
import re

def test_extraction(content):
    extracted = {
        'destination': None,
        'origin': None,
        'days': None,
        'budget': None,
        'travellers': None,
        'trip_style': None,
        'mood': None
    }
    
    # Simulating the fix logic
    json_match = re.search(r'\{.*\}', content, re.DOTALL)
    if json_match:
        try:
            llm_data = json.loads(json_match.group())
            for k in extracted.keys():
                if llm_data.get(k) is not None:
                    extracted[k] = llm_data[k]
        except Exception as e:
            print(f"JSON Error: {e}")
    else:
        print("DEBUG: No JSON found in LLM response")
        
    return extracted

# Test Case 1: Natural sentence with chatter
chatter_response = """Sure, I can help with that! Based on your request, here are the extracted details:
{
    "destination": "Ooty",
    "days": 3,
    "budget": 20000,
    "travellers": 2
}
I hope this helps!"""

print("Test Case 1 (Chatter):")
result1 = test_extraction(chatter_response)
print(f"Result: {result1}")

# Test Case 2: Natural sentence (no JSON) - fallback to regex (simulated here)
query = "I want to go to Munnar for 5 days with a 30k budget"
print("\nTest Case 2 (Query for Regex Safety Net):")
# Simulated regex safety net
extracted2 = {'destination': None, 'days': None, 'budget': None}
match_days = re.search(r'(\d+)\s*days?', query.lower())
if match_days: extracted2['days'] = int(match_days.group(1))

match_budget = re.search(r'(\d+)\s*k', query.lower())
if match_budget: extracted2['budget'] = float(match_budget.group(1)) * 1000

# Simulated city match
cities = [{"name": "Munnar"}, {"name": "Ooty"}]
for city in cities:
    if city['name'].lower() in query.lower():
        extracted2['destination'] = city['name']

print(f"Result: {extracted2}")
