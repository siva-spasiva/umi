import sys
import os
import json
import asyncio
import httpx

# 프로젝트 최상단 경로를 sys.path에 추가하여 'app' 모듈을 찾을 수 있게 합니다.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.core.security import get_current_user_id

# [인증 우회] 테스트를 위해 가짜 유저 ID를 주입합니다.
def mock_get_current_user_id() -> str:
    return "test_map_user_999"

app.dependency_overrides[get_current_user_id] = mock_get_current_user_id

# [LLMEngine 우회] Event loop is closed 에러 방지를 위해 요약 로직 모킹
from app.api.v1.chat import llm_engine
async def mock_save_session_summary(day_index: int, npc_id: str, user_id: str):
    return [{"npc_id": "mock", "summary": "mock summary"}]
llm_engine.save_session_summary = mock_save_session_summary


async def test_end_session_map_generation(client: httpx.AsyncClient):
    """
    /end-session API를 호출하여 next_session_map 구조가 잘 생상되는지 확인합니다.
    (day_index=1, session_index=1 -> 예상: day 1, session 2 (afternoon))
    """
    payload = {
        "day_index": 1,
        "session_index": 1,
        "npc_id": "mineo"  # 임의 지정
    }
    
    response = await client.post("/api/v1/end-session", json=payload)
    
    assert response.status_code == 200, f"API 호출 실패: {response.text}"
    
    data = response.json()
    assert "next_session_map" in data, "응답에 next_session_map 키가 누락되었습니다."
    
    next_map = data["next_session_map"]
    print("\n\n====== [ Test 1: Day 1, Session 1 -> Next: Day 1, Session 2 ] ======")
    print(f"Next Day: {next_map['day_index']}")
    print(f"Next Session: {next_map['session_index']} ({next_map['session_name']})")
    print(json.dumps(next_map['room_placements'], indent=2, ensure_ascii=False))
    
    assert next_map['day_index'] == 1
    assert next_map['session_index'] == 2
    assert next_map['session_name'] == "afternoon"
    assert len(next_map['room_placements']) > 0


async def test_end_session_day_rollover(client: httpx.AsyncClient):
    """
    /end-session API에서 session_index=4 (night)일 경우 다음 날로 넘어가는지 확인합니다.
    (day_index=1, session_index=4 -> 예상: day 2, session 1 (morning))
    """
    payload = {
        "day_index": 1,
        "session_index": 4
    }
    
    response = await client.post("/api/v1/end-session", json=payload)
    
    assert response.status_code == 200, f"API 호출 실패: {response.text}"
    
    data = response.json()
    next_map = data["next_session_map"]
    
    print("\n\n====== [ Test 2: Day 1, Night(4) -> Next: Day 2, Morning(1) ] ======")
    print(f"Next Day: {next_map['day_index']}")
    print(f"Next Session: {next_map['session_index']} ({next_map['session_name']})")
    print(json.dumps(next_map['room_placements'], indent=2, ensure_ascii=False))
    
    assert next_map['day_index'] == 2
    assert next_map['session_index'] == 1
    assert next_map['session_name'] == "morning"


async def test_topic_assignment(client: httpx.AsyncClient):
    """
    Day 3, Session 1을 종료하면 -> Day 3, Session 2 (afternoon)가 다음 세션.
    이때 chapel에 전광어(JEONGGWANGEO)와 곽빙어(GWAKBINGEO)가 함께 배치되어 topic이 할당되어야 합니다.
    """
    payload = {
        "day_index": 3,
        "session_index": 1
    }
    
    response = await client.post("/api/v1/end-session", json=payload)
    
    assert response.status_code == 200, f"API 호출 실패: {response.text}"
    
    data = response.json()
    next_map = data["next_session_map"]
    
    print("\n\n====== [ Test 3: Day 3, Morning(1) -> Next: Day 3, Afternoon(2) ] ======")
    print(f"Next Day: {next_map['day_index']}")
    print(f"Next Session: {next_map['session_index']} ({next_map['session_name']})")
    print(json.dumps(next_map['room_placements'], indent=2, ensure_ascii=False))
    
    assert next_map['day_index'] == 3
    assert next_map['session_index'] == 2
    assert next_map['session_name'] == "afternoon"
    
    # chapel에 2명이 겹치므로 topic이 null이 아니어야 합니다
    chapel_entry = None
    for placement in next_map['room_placements']:
        if placement['room_id'] == 'chapel':
            chapel_entry = placement
            break
    
    assert chapel_entry is not None, "chapel 방 배치 정보가 없습니다."
    assert len(chapel_entry['npcs']) >= 2, f"chapel에 NPC가 2명 이상이어야 합니다. 현재: {chapel_entry['npcs']}"
    assert chapel_entry['topic'] is not None, "chapel에 2명 이상 NPC가 있는데 topic이 null입니다!"
    
    print(f"\n  🎯 chapel에서 겹침 발생!")
    print(f"     NPCs: {chapel_entry['npcs']}")
    print(f"     Topic: {chapel_entry['topic']['title']}")


async def main():
    print("🚀 /end-session 맵 및 주제 구성 API 테스트를 시작합니다...")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await test_end_session_map_generation(client)
        await test_end_session_day_rollover(client)
        await test_topic_assignment(client)
    print("\n✅ 모든 맵 매핑 테스트 통과!")


if __name__ == "__main__":
    asyncio.run(main())
