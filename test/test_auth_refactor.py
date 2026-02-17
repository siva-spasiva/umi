import asyncio
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.user_service import user_service
from app.services.stats_service import stats_service
from app.api.v1.user import login as login_endpoint
from app.api.v1.stats import static_stats as static_stats_endpoint

async def test_auth_refactor():
    print("=== API Authentication Refactor Test ===")

    # 1. Test Login (Token Issuance)
    print("\n[Step 1] Testing /users/login (Token Issuance)...")
    
    # Mock DB insert for login
    user_service.collection_token = AsyncMock()
    user_service.collection_token.insert_one = AsyncMock(return_value=True)
    
    login_response = await login_endpoint()
    print(f"Login Response: {login_response}")
    
    access_token = login_response["access_token"]
    # user_id is no longer returned
    
    assert access_token is not None, "Access token missing"
    print("✅ Login Successful")

    # 2. Test Static Stats (Stats Init with Token)
    print("\n[Step 2] Testing /stats/static (Stats Init with Token)...")
    
    # helper to decode token and get user_id (since it's not in response)
    import jwt
    decoded = jwt.decode(access_token, options={"verify_signature": False})
    user_id = decoded["sub"]
    
    # Mock DB inserts for stats init
    stats_service.collection_token = AsyncMock()
    stats_service.collection_token.insert_one = AsyncMock(return_value=True)
    stats_service.collection_npc = AsyncMock()
    stats_service.collection_npc.insert_many = AsyncMock(return_value=True)
    stats_service.db = MagicMock()
    stats_service.db.__getitem__ = MagicMock(return_value=AsyncMock()) # for inventories
    
    # Mock character data loading
    with patch("builtins.open", new_callable=MagicMock) as mock_open:
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = '{"believer_a": {"friendly": 10}}'
        mock_open.return_value = mock_file
        
        # Call endpoint with mock user_id (simulating Depends(get_current_user_id))
        stats_response = await static_stats_endpoint(user_id=user_id)
        print(f"Stats Response: {stats_response}")
        
        # Check that token is NOT in response
        assert "token" not in stats_response, "Token should NOT be in stats response"
        assert stats_response["hp"] == 100, "HP should be 100"
        print("✅ Stats Init Successful (No Token in Response)")

    print("\n🎉 All Auth Refactor Tests Passed!")

if __name__ == "__main__":
    try:
        asyncio.run(test_auth_refactor())
    except Exception as e:
        print(f"❌ Test failed: {e}")
        exit(1)
