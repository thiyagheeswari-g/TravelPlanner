import json
from agent import TravelAgent

def test_phases():
    agent = TravelAgent()
    history = []
    
    # PHASE 1: Minimalist Test
    print("\n--- PHASE 1: Minimalist Test ---")
    input1 = {"query": "Plan a trip to Ooty", "chat_history": history}
    state1 = agent.run(input1)
    print(f"Dest: {state1['destination']}, Days: {state1['days']}, Travellers: {state1['travellers']}, Budget: {state1['budget']}")
    print(f"Response: {state1['final_response'][:200]}...")
    
    # Store for next turn
    history.append({"role": "user", "content": input1["query"]})
    history.append({"role": "assistant", "content": state1["final_response"]})
    
    # PHASE 2: Stateful Memory
    print("\n--- PHASE 2: Stateful Memory ---")
    input2 = {
        "query": "Actually 5 people & Adventure mood", 
        "chat_history": history,
        "destination": state1['destination'],
        "days": state1['days'],
        "travellers": state1['travellers'],
        "budget": state1['budget'],
        "mood": state1['mood']
    }
    state2 = agent.run(input2)
    print(f"Dest: {state2['destination']}, Days: {state2['days']}, Travellers: {state2['travellers']}, Budget: {state2['budget']}, Mood: {state2['mood']}")
    print(f"Changes: {state2['field_changes']}")
    print(f"Response: {state2['final_response'][:200]}...")

    # Store for next turn
    history.append({"role": "user", "content": input2["query"]})
    history.append({"role": "assistant", "content": state2["final_response"]})

    # PHASE 3: Budget Stress
    print("\n--- PHASE 3: Budget Stress ---")
    input3 = {
        "query": "Change budget to 10k", 
        "chat_history": history,
        "destination": state2['destination'],
        "days": state2['days'],
        "travellers": state2['travellers'],
        "budget": state2['budget'],
        "mood": state2['mood']
    }
    state3 = agent.run(input3)
    print(f"Dest: {state3['destination']}, Days: {state3['days']}, Travellers: {state3['travellers']}, Budget: {state3['budget']}")
    print(f"Changes: {state3['field_changes']}")
    print(f"Response: {state3['final_response'][:200]}...")

if __name__ == "__main__":
    test_phases()
