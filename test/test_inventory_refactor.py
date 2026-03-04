import sys
import os
import asyncio
import httpx
import uuid

# 프로젝트 최상단 경로를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.core.security import get_current_user_id

# 새로운 랜덤 유저 ID 생성 (신규 유저 테스트용)
random_user_id = f"test_user_{uuid.uuid4().hex[:8]}"
print(f"Test User ID: {random_user_id}")

# [인증 우회]
def mock_get_current_user_id() -> str:
    return random_user_id

app.dependency_overrides[get_current_user_id] = mock_get_current_user_id

async def test_new_user_starting_items():
    """신규 유저 인벤토리 조회 시 시작 아이템 3종(001, 002, 003)이 있는지 확인"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        print("\n🚀 [Test] 신규 유저 인벤토리 조회 테스트 시작...")
        response = await client.get("/api/v1/inventory")
        assert response.status_code == 200
        data = response.json()
        
        # 1. 응답 구조 확인
        assert "user_id" in data
        assert "items" in data
        assert isinstance(data["items"], list) # 리스트 형태여야 함
        
        # 2. 시작 아이템 소유 여부 확인
        items = data["items"]
        owned_ids = [item["id"] for item in items if item["owned"]]
        print(f"보유 중인 아이템: {owned_ids}")
        
        for start_id in ["item001", "item002", "item003"]:
            assert start_id in owned_ids, f"시작 아이템 {start_id}을(를) 보유하고 있지 않습니다."
            
        # 3. 상세 정보 포함 여부 확인
        sample_item = next(item for item in items if item["id"] == "item001")
        assert "name" in sample_item and sample_item["name"] == "스마트폰"
        assert "description" in sample_item
        assert "type" in sample_item
        print("✅ Test 1: 신규 유저 시작 아이템 및 상세 정보 반환 확인 완료")

async def test_add_item_and_detailed_response():
    """아이템 추가 시에도 상세 정보가 포함된 전체 리스트를 반환하는지 확인"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        print("\n🚀 [Test] 아이템 추가 API 테스트 시작...")
        # item005 (솔피의 눈물) 추가
        payload = {"item_id": "item005"}
        response = await client.post("/api/v1/inventory/add", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        items = data["items"]
        # item005가 owned=True 인지 확인
        item005 = next(item for item in items if item["id"] == "item005")
        assert item005["owned"] == True
        assert item005["name"] == "솔피의 눈물"
        
        owned_ids = [item["id"] for item in items if item["owned"]]
        print(f"아이템 추가 후 보유 목록: {owned_ids}")
        assert "item005" in owned_ids
        
        print("✅ Test 2: 아이템 추가 및 자동 리프레시 상세 응답 확인 완료")

async def main():
    try:
        await test_new_user_starting_items()
        await test_add_item_and_detailed_response()
        print("\n🎉 모든 인벤토리 테스트 통과!")
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
