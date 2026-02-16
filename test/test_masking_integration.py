import asyncio
import os
import os
import sys
from unittest.mock import AsyncMock, patch, MagicMock

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.chat_service import chat_service

async def test_masking_integration():
    print("=== Word Masking Integration Test (ChatService) ===")

    # Mock Data
    user_id = "test_user"
    npc_id = "NPC_CHEONG_02"
    message = "안녕"
    
    # 1. Test Case: High Fish Level (Should Mask)
    print("\n[Case 1] Fish Level 3 (Masking Expected)")
    
    mock_response_text = "어머니 바다의 축복이 있기를. 교주님을 믿으세요."
    expected_masked = "뻐끔의 뻐끔이 있기를. 뻐끔님을 믿으세요."
    
    mock_llm_result = {
        "response": mock_response_text,
        "analysis": {},
        "state": {"fish_level": 3}  # Threshold triggered
    }

    # Patch dependencies
    with patch("app.services.chat_service.ga_agent") as mock_ga, \
         patch("app.services.chat_service.ga1_agent") as mock_ga1, \
         patch("app.services.chat_service.llm_engine") as mock_llm:
         
        # Setup Mocks
        mock_ga.validate_input = AsyncMock(return_value=(True, message))
        mock_ga1.check_safety = AsyncMock(return_value=(True, message))
        mock_llm.ask = AsyncMock(return_value=mock_llm_result)
        mock_ga.validate_output = AsyncMock(side_effect=lambda x: (True, x)) # Return input as output

        # Execute
        result = await chat_service.process_chat_flow(user_id, npc_id, message)
        
        final_response = result["response"]
        print(f"Original (Mocked): {mock_response_text}")
        print(f"Final Response:    {final_response}")
        
        assert "뻐끔" in final_response
        assert "어머니 바다" not in final_response
        assert "교주" not in final_response
        print("✅ Case 1 Passed")

    # 2. Test Case: Low Fish Level (Should NOT Mask)
    print("\n[Case 2] Fish Level 1 (No Masking)")
    
    mock_llm_result_low = {
        "response": mock_response_text,
        "analysis": {},
        "state": {"fish_level": 1}  # Not triggered
    }

    with patch("app.services.chat_service.ga_agent") as mock_ga, \
         patch("app.services.chat_service.ga1_agent") as mock_ga1, \
         patch("app.services.chat_service.llm_engine") as mock_llm:
         
        mock_ga.validate_input = AsyncMock(return_value=(True, message))
        mock_ga1.check_safety = AsyncMock(return_value=(True, message))
        mock_llm.ask = AsyncMock(return_value=mock_llm_result_low)
        mock_ga.validate_output = AsyncMock(side_effect=lambda x: (True, x))

        result = await chat_service.process_chat_flow(user_id, npc_id, message)
        
        final_response = result["response"]
        print(f"Final Response:    {final_response}")
        
        assert "뻐끔" not in final_response
        assert "어머니 바다" in final_response
        print("✅ Case 2 Passed")

    # 3. Test Case: Heavy Masking (NPC=5, User=1 -> Diff=4 >= 2)
    print("\n[Case 3] Heavy Masking (NPC=5, User=1 -> Diff=4)")
    
    mock_llm_result_heavy = {
        "response": mock_response_text,
        "analysis": {},
        "state": {"fish_level": 5}
    }
    
    # Mock DB for user_state
    mock_db_collection = AsyncMock()
    mock_db_collection.find_one = AsyncMock(return_value={"fish_level": 1})

    with patch("app.services.chat_service.ga_agent") as mock_ga, \
         patch("app.services.chat_service.ga1_agent") as mock_ga1, \
         patch("app.services.chat_service.llm_engine") as mock_llm:
         
        mock_ga.validate_input = AsyncMock(return_value=(True, message))
        mock_ga1.check_safety = AsyncMock(return_value=(True, message))
        mock_llm.ask = AsyncMock(return_value=mock_llm_result_heavy)
        mock_ga.validate_output = AsyncMock(side_effect=lambda x: (True, x))
        
        # Inject mock DB correctly using side_effect on __getitem__
        chat_service.db.__getitem__ = MagicMock(return_value=mock_db_collection)

        result = await chat_service.process_chat_flow(user_id, npc_id, message)
        
        final_response = result["response"]
        print(f"Original: {mock_response_text}")
        print(f"Final:    {final_response}")
        
        # Check forbidden words are masked (100%)
        assert "어머니 바다" not in final_response, "Forbidden word leaked"
        assert "교주" not in final_response, "Forbidden word leaked"
        
        # Check heavy masking (should be many "뻐끔")
        pt_count = final_response.count("뻐끔")
        print(f"Mask Count: {pt_count}")
        assert pt_count >= 3, "Not enough masking for heavy mode" # Expecting high ratio
        print("✅ Case 3 Passed")

if __name__ == "__main__":
    try:
        asyncio.run(test_masking_integration())
    except Exception as e:
        print(f"❌ Test failed: {e}")
        exit(1)
