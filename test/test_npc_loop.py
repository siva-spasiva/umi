import requests
import json
import time
import sys

# Configuration
API_URL = "http://localhost:8001"
NPC_IDS = ["gwakbing", "cheonggalchi", "bakbok", "jeongwang", "mineo"]
MAX_TURNS = 7

# Predefined user scenarios for 7 turns
# Designed to test: Greeting -> Lore -> Personal -> Trade/Secret -> Faith/Danger -> Conflict -> Resolution
SCENARIOS = [
    "안녕, 여기서 뭐 하고 있어?",  # 1. Greeting
    "솔피가 정확히 뭐야? 사람들이 무서워하던데.",  # 2. Lore (RAG Check)
    "여기서 나가는 방법 알아? 도와주면 사례할게.",  # 3. Goal/Trade
    "전광어 교주님은 어떤 분이야? 믿을 만해?",  # 4. Key Figure
    "내 방에 수상한 물건이 있던데 네 거야?",  # 5. Conflict/Suspicion
    "솔직히 말해. 이 교단 이상하잖아. 같이 도망치자.",  # 6. Persuasion (High Stakes)
    "알겠어. 일단 네 말대로 할게. 다음엔 어떻게 해?"  # 7. Agreement/Next Step
]

def check_server():
    try:
        resp = requests.get(f"{API_URL}/health")
        if resp.status_code == 200:
            print(f"✅ Server is running at {API_URL}")
            info = resp.json()
            print(f"   Models loaded: {info.get('models')}")
            return True
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to {API_URL}. Please ensure 'gpu_server.py' is running.")
        return False
    return False

def test_npc_loop():
    if not check_server():
        sys.exit(1)

    print(f"\n🚀 Starting V2 NPC Conversation Loop Test ({MAX_TURNS} turns)")
    print(f"Target NPCs: {NPC_IDS}")
    
    for npc_id in NPC_IDS:
        print(f"\n{'='*60}")
        print(f"Testing NPC: {npc_id.upper()}")
        print(f"{'='*60}")
        
        history = []
        
        for i in range(MAX_TURNS):
            user_msg = SCENARIOS[i] if i < len(SCENARIOS) else "..."
            
            print(f"\n[Turn {i+1}/{MAX_TURNS}]")
            print(f"User: {user_msg}")
            
            payload = {
                "npc_id": npc_id,
                "message": user_msg,
                "history": history
            }
            
            start_ts = time.time()
            try:
                resp = requests.post(f"{API_URL}/infer/npc", json=payload)
                resp.raise_for_status()
                data = resp.json()
                latency = time.time() - start_ts
                
                npc_response = data["response"]
                analysis = data.get("analysis", {})
                state = data.get("state", {})
                
                print(f"NPC : {npc_response}")
                print(f"   > Latency: {latency:.2f}s")
                print(f"   > State: Friendly={state.get('friendly')}, Faith={state.get('faith')}")
                print(f"   > Analysis: {analysis.get('reason_tags')} | Delta: F{analysis.get('friendly_delta'):+d}/M{analysis.get('faith_delta'):+d}")
                
                # Append to history for context continuity
                history.append({"speaker": "user", "content": user_msg})
                history.append({"speaker": npc_id, "content": npc_response})
                
                # Check for RAG usage (simple heuristic)
                if i == 1: # Lore question
                    print("   > [Checkpoint] Checking lore response...")
                    # Note: We can't easily verify RAG content without knowing the lore text, 
                    # but looking at the response length and content might give a hint.
                
            except Exception as e:
                print(f"❌ Error on Turn {i+1}: {e}")
                break
                
        print(f"\n✅ {npc_id} test finished.")

if __name__ == "__main__":
    test_npc_loop()
