import requests
import json
import sys

API_URL = "http://localhost:8001/infer/npc"

# Key terms expected in responses for specific queries
LORE_TESTS = [
    {
        "npc_id": "cheonggalchi",
        "question": "솔피가 정확히 뭐야?",
        "keywords": ["범고래", "신수", "눈물", "바다"],
        "forbidden": ["모른다", "글쎄"] 
    },
    {
        "npc_id": "gwakbing", 
        "question": "전광어 교주는 어떤 사람이야?",
        "keywords": ["교주", "믿음", "의심", "아버지", "인도자"], 
        "forbidden": []
    },
    {
        "npc_id": "jeongwang",
        "question": "이 교단의 목적이 무엇입니까?",
        "keywords": ["구원", "정화", "바다", "육지", "평화"],
        "forbidden": ["모릅니다"]
    }
]

def test_rag_lore():
    print(f"\n🚀 Starting RAG Lore Verification Test")
    
    for test in LORE_TESTS:
        npc_id = test["npc_id"]
        q = test["question"]
        print(f"\nTesting {npc_id} with query: '{q}'")
        
        payload = {
            "npc_id": npc_id,
            "message": q,
            "history": []
        }
        
        try:
            resp = requests.post(API_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
            
            answer = data["response"]
            print(f"Answer: {answer}")
            
            # Check keywords (Case-insensitive)
            found = []
            answer_lower = answer.lower()
            for kw in test["keywords"]:
                if kw.lower() in answer_lower:
                    found.append(kw)
            
            print(f"   > Keywords found: {found} / {test['keywords']}")
            
            if len(found) > 0:
                print("   ✅ RAG likely working (relevant keywords found)")
            else:
                print("   ⚠️ RAG might have failed or NPC is being evasive.")
                
            # Check forbidden
            for fb in test["forbidden"]:
                if fb in answer:
                    print(f"   ⚠️ Forbidden word '{fb}' found (NPC might be feigning ignorance)")
                    
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_rag_lore()
