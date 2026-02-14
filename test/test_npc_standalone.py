import sys
import os
import time

# 프로젝트 루트 경로를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.agents.npc_agent_fixed import npc_agent

def test_generation():
    print("\n--- NPC Agent Standalone Test ---")
    prompt = "User: 안녕? 넌 누구니?\nNPC:"
    
    print(f"Input Prompt: {prompt}")
    print("Generating... (Please wait)")
    
    start_time = time.time()
    try:
        # 동기적으로 호출
        response = npc_agent.generate(prompt, max_new_tokens=50)
        end_time = time.time()
        print(f"\nResponse: {response}")
        print(f"⏱️ 소요 시간: {end_time - start_time:.2f}초")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_generation()