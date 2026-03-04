import requests
import json
import time

def test_npc_conversation():
    url = "http://127.0.0.1:8000/api/v1/conversation/start"
    
    headers = {
        "Authorization": "Bearer magic_token_for_test",
        "Content-Type": "application/json"
    }
    
    payload = {
        "topic": "random",
        "npc_ids": ["NPC_CHEONG_02", "NPC_KWAK_01"],
        "num_turns": 4
    }
    
    print(f"🚀 Sending request to {url}...")
    print(f"Payload: {json.dumps(payload, ensure_ascii=False)}")
    
    try:
        start_time = time.time()
        response = requests.post(url, json=payload, headers=headers)
        elapsed = time.time() - start_time
        
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            data = data[0]
        
        print(f"\n✅ Success! ({elapsed:.2f}s)")
        print(f"Topic: {data.get('topic')}")
        
        turns = data.get("turns", [])
        print(f"Turns: {len(turns)}")
        
        for i, turn in enumerate(turns):
            print(f"\n[{i+1}] {turn.get('speaker')} ({turn.get('speaker_id')})")
            print(f"    {turn.get('content')}")
            analysis = turn.get('analysis')
            if analysis:
                print(f"    [Analysis] Friendly: {analysis.get('friendly_delta')}, Faith: {analysis.get('faith_delta')}")
        
        print("\n🔍 NPC States (Should be unchanged from previous or default):")
        print(json.dumps(data.get("npc_states"), indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if 'response' in locals() and response:
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")

if __name__ == "__main__":
    test_npc_conversation()
