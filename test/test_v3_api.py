
import requests
import json
import time

API_URL = "http://127.0.0.1:8000/api/v1"
HEADERS = {
    "Authorization": "Bearer magic_token_for_test",
    "Content-Type": "application/json"
}

def test_chat_api():
    print("🚀 Testing V3 Chat API (/api/v1/chat)...")
    
    npc_id = "gwakbing"
    message = "안녕, 너는 누구야? 그리고 여기서 뭐하고 있어?"
    
    payload = {
        "npcId": npc_id,
        "message": message
    }
    
    start_time = time.time()
    try:
        response = requests.post(f"{API_URL}/chat", headers=HEADERS, json=payload)
        response.raise_for_status()
        data = response.json()
        latency = time.time() - start_time
        
        print(f"✅ Response received in {latency:.2f}s")
        print(f"Status: {data.get('status')}")
        print(f"NPC ID: {data.get('npcId')}")
        print(f"Response: {data.get('response')}")
        print(f"Analysis: {data.get('analysis')}")
        print(f"State: {data.get('state')}")
        
        # Assertions
        assert data.get("status") in ["success", "sanitized"], f"Unexpected status: {data.get('status')}"
        assert data.get("npcId") == npc_id
        assert data.get("response") and len(data.get("response")) > 0
        assert "analysis" in data
        assert "state" in data
        
        print("\n🎉 API Verification Passed!")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ API Request Failed: {e}")
        if e.response:
            print(f"Response Body: {e.response.text}")
        return False
    except AssertionError as e:
        print(f"❌ Assertion Failed: {e}")
        return False

if __name__ == "__main__":
    test_chat_api()
