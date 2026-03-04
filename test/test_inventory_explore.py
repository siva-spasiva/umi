import asyncio
import os
import sys
import uuid

import httpx

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.core.database import db
from app.core.security import get_current_user_id


test_user_id = f"explore_test_{uuid.uuid4().hex[:8]}"
test_floor_id = f"TST_FLOOR_{uuid.uuid4().hex[:6]}"
test_room_id = "test_room"
test_zone_with_item = "zone_with_item"
test_zone_no_item = "zone_no_item"
test_item_id = f"test_item_{uuid.uuid4().hex[:6]}"


def mock_get_current_user_id() -> str:
    return test_user_id


app.dependency_overrides[get_current_user_id] = mock_get_current_user_id


async def seed_test_data():
    await db["maps"].insert_one({
        "id": test_floor_id,
        "name": "테스트 층",
        "description": "탐색 API 테스트용 맵",
        "rooms": [
            {
                "id": test_room_id,
                "name": "테스트 방",
                "description": "테스트 방 설명",
                "activeZones": [
                    {
                        "id": test_zone_with_item,
                        "type": "item",
                        "target": "",
                        "x": 10,
                        "y": 10,
                        "width": 10,
                        "height": 10,
                        "label": "상자",
                        "message": "수상한 상자",
                        "itemId": test_item_id
                    },
                    {
                        "id": test_zone_no_item,
                        "type": "info",
                        "target": "",
                        "x": 30,
                        "y": 30,
                        "width": 10,
                        "height": 10,
                        "label": "빈 공간",
                        "message": "아무것도 없다",
                        "itemId": ""
                    }
                ]
            }
        ]
    })

    await db["items"].insert_one({
        "id": test_item_id,
        "name": "테스트 아이템",
        "description": "탐색으로 얻는 테스트 아이템",
        "flavorText": "테스트 전용",
        "type": "normal"
    })


async def test_explore_item_found(client: httpx.AsyncClient):
    resp = await client.post("/api/v1/inventory/explore", json={
        "floor_id": test_floor_id,
        "room_id": test_room_id,
        "active_zone_id": test_zone_with_item
    })
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["success"] is True
    assert data["item_found"] is True
    assert data["item"]["id"] == test_item_id
    assert data["item"]["owned"] is True

    inventory = await db["inventories"].find_one({"user_id": test_user_id}, {"_id": 0})
    assert inventory is not None
    assert inventory.get("items", {}).get(test_item_id) is True

    event = await db["item_events"].find_one(
        {"user_id": test_user_id, "item_id": test_item_id, "action": "acquired"},
        sort=[("timestamp", -1)]
    )
    assert event is not None

    print("✅ 아이템 발견/획득 및 인벤토리 반영 검증 완료")


async def test_explore_no_item(client: httpx.AsyncClient):
    resp = await client.post("/api/v1/inventory/explore", json={
        "floor_id": test_floor_id,
        "room_id": test_room_id,
        "active_zone_id": test_zone_no_item
    })
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["success"] is True
    assert data["item_found"] is False
    assert data["item"] is None

    print("✅ 아이템 없는 구역 응답 검증 완료")


async def test_explore_invalid_zone(client: httpx.AsyncClient):
    resp = await client.post("/api/v1/inventory/explore", json={
        "floor_id": test_floor_id,
        "room_id": test_room_id,
        "active_zone_id": "not_exist_zone"
    })
    assert resp.status_code == 404, resp.text
    assert "액티브존을 찾을 수 없습니다" in resp.text

    print("✅ 잘못된 액티브존 404 검증 완료")


async def main():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            await seed_test_data()
            await test_explore_item_found(client)
            await test_explore_no_item(client)
            await test_explore_invalid_zone(client)
            print("\n🎉 inventory/explore 테스트 통과")
        except Exception as e:
            print(f"\n❌ 테스트 실패: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print("\n🧹 [Cleanup] 테스트 데이터 삭제 중...")
            await db["item_events"].delete_many({"user_id": test_user_id, "item_id": test_item_id})
            await db["inventories"].delete_many({"user_id": test_user_id})
            await db["items"].delete_many({"id": test_item_id})
            await db["maps"].delete_many({"id": test_floor_id})
            print("✅ [Cleanup] 완료")


if __name__ == "__main__":
    asyncio.run(main())
