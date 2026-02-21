import sys
import os
import json
import asyncio
import httpx

# 프로젝트 최상단 경로를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.core.security import get_current_user_id

# [인증 우회]
def mock_get_current_user_id() -> str:
    return "test_eavesdrop_user"

app.dependency_overrides[get_current_user_id] = mock_get_current_user_id


async def test_room_without_eavesdrop(client: httpx.AsyncClient):
    """day_index/session_index 없이 방 조회 → eavesdrop은 null"""
    response = await client.get("/api/v1/map/B1/room/cafeteria")
    assert response.status_code == 200
    data = response.json()
    assert "room" in data
    assert data["eavesdrop"] is None
    print("\n✅ Test 1: 방 조회 (파라미터 없음) → eavesdrop=null 정상")


async def test_room_no_overlap(client: httpx.AsyncClient):
    """NPC가 겹치지 않는 방 → eavesdrop=null"""
    # Day 1, Session 2(afternoon)의 cafeteria에는 GWAKBINGEO 혼자
    response = await client.get("/api/v1/map/B1/room/cafeteria?day_index=1&session_index=2")
    assert response.status_code == 200
    data = response.json()
    assert data["eavesdrop"] is None
    print("✅ Test 2: NPC 1명인 방 → eavesdrop=null 정상")


async def test_room_with_eavesdrop(client: httpx.AsyncClient):
    """Day 3, Session 2(afternoon) chapel에 전광어+곽빙어 → 엿듣기 대화 생성!"""
    response = await client.get("/api/v1/map/B3/room/chapel?day_index=3&session_index=2")
    assert response.status_code == 200
    data = response.json()
    
    print("\n====== [ Test 3: Day 3 Afternoon - Chapel 엿듣기 ] ======")
    
    if data["eavesdrop"] is None:
        print("⚠️ eavesdrop이 null입니다. (GPU 서버 미연결 시 정상일 수 있음)")
        return
    
    eavesdrop = data["eavesdrop"]
    print(f"NPCs: {eavesdrop['npcs']}")
    print(f"Topic: {eavesdrop['topic']['title']}")
    print(f"대화 턴 수: {len(eavesdrop['conversation']['turns'])}")
    
    for turn in eavesdrop["conversation"]["turns"]:
        print(f"  [{turn['speaker']}] {turn['content'][:80]}...")
    
    assert eavesdrop["can_eavesdrop_more"] == True
    assert len(eavesdrop["npcs"]) >= 2
    assert len(eavesdrop["conversation"]["turns"]) == 6
    print("✅ Test 3: 엿듣기 대화 6턴 생성 확인!")


async def test_eavesdrop_more(client: httpx.AsyncClient):
    """POST /eavesdrop으로 추가 엿듣기 (day/session/room만 전달)"""
    payload = {
        "day_index": 3,
        "session_index": 2,
        "room_id": "chapel"
    }
    
    response = await client.post("/api/v1/map/eavesdrop", json=payload)
    assert response.status_code == 200, f"API 호출 실패: {response.text}"
    data = response.json()
    
    print("\n====== [ Test 4: 추가 엿듣기 (POST /eavesdrop) ] ======")
    
    conv = data["conversation"]
    print(f"대화 턴 수: {len(conv['turns'])}")
    for turn in conv["turns"]:
        print(f"  [{turn['speaker']}] {turn['content'][:80]}...")
    
    assert data["can_eavesdrop_more"] == True
    assert len(conv["turns"]) == 6
    print("✅ Test 4: 추가 엿듣기 6턴 생성 확인!")


async def main():
    print("🚀 엿듣기(Eavesdrop) API 테스트 시작...")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await test_room_without_eavesdrop(client)
        await test_room_no_overlap(client)
        await test_room_with_eavesdrop(client)
        await test_eavesdrop_more(client)
    print("\n🎉 모든 엿듣기 테스트 완료!")


if __name__ == "__main__":
    asyncio.run(main())
