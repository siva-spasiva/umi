import asyncio
import sys
import os

# 프로젝트 루트 경로 추가 (모듈 import를 위해)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.chat_service import chat_service
from app.core.database import db

async def test_troll_system():
    print("🧪 [Test] Troll Level System Testing Start")
    
    # 테스트용 유저 ID
    test_user_id = "test_troll_user_001"
    npc_id = "shibuya_rin" # 임의의 NPC
    
    # 1. 초기 상태 리셋 (DB Clean up)
    # db가 이미 database 객체이므로 함수 호출() 불필요
    await db["user_states"].delete_one({"user_id": test_user_id})
    await db["story_summaries"].delete_many({"day_index": {"$gte": 1}}) # 테스트용 요약 삭제
    print(f"✅ User {test_user_id} state reset.")

    # 2. 트롤 메시지 전송 (3회 반복)
    troll_message = "야 이 바보 멍청이 해삼  말미잘" # Basic Guardrail 또는 GA1에 걸릴만한 메시지
    
    for i in range(1, 4):
        print(f"\n📨 [Test] Sending Troll Message ({i}/3)...")
        result = await chat_service.process_chat_flow(test_user_id, npc_id, troll_message)
        
        status = result.get("status")
        response = result.get("response")
        force_skip = result.get("force_skip", False)
        
        print(f"   => Status: {status}")
        print(f"   => Response: {response[:50]}...")
        
        if i < 3:
            # 1, 2번째는 그냥 차단만 되어야 함
            if status not in ["blocked_by_guardrail", "blocked_by_ga1", "blocked_by_ga2"]:
                print(f"❌ [Fail] Expected blocked status, got {status}")
                return
            if force_skip:
                print(f"❌ [Fail] Force skip triggered too early!")
                return
            print(f"✅ Warning {i} confirmed.")
            
        else:
            # 3번째는 강제 스킵이 되어야 함
            if not force_skip:
                 print(f"❌ [Fail] Force skip NOT triggered on 3rd attempt!")
                 return
            if status != "blocked_by_troll_limit":
                 print(f"❌ [Fail] Expected 'blocked_by_troll_limit', got {status}")
                 return
            print(f"✅ Force Skip Triggered correctly!")

    # 3. DB 상태 확인 (요약 생성 여부)
    summary = await db["story_summaries"].find_one({"previous_day_index": 1}) # 로직상 day_index가 갱신되었으므로, 요약은 이전 날짜(혹은 1일차)로 저장되었는지 확인
    # *참고*: _skip_to_next_day 구현에서 day_index(1)로 요약을 저장했음.
    
    summary = await db["story_summaries"].find_one({"day_index": 1})
    # StorySummary 스키마에는 'summary' 필드가 없고 'summary_bullets' 리스트가 있음
    if summary and any("불손한 태도" in bullet for bullet in summary.get("summary_bullets", [])):
        print(f"✅ [Success] Bad Ending Summary created for Day 1.")
    else:
        print(f"❌ [Fail] Bad Ending Summary not found or content mismatch.")
        print(f"   Stored Summary: {summary.get('summary_bullets') if summary else 'None'}")

    # 4. User State 확인 (Day Index가 2로 넘어가야 함)
    user_state = await db["user_states"].find_one({"user_id": test_user_id})
    if user_state["day_index"] == 2 and user_state["troll_count"] == 0:
        print(f"✅ [Success] User moved to Day 2, troll count reset.")
    else:
        print(f"❌ [Fail] User State mismatch: {user_state}")

if __name__ == "__main__":
    asyncio.run(test_troll_system())
