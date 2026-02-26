import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.chat_service import chat_service

async def test_fish_level_masking():
    print("=== Fish Level Masking Logic Test ===")

    user_id = "test_user"
    npc_id = "test_npc"
    message = "안녕"
    mock_response_text = "이 텍스트는 마스킹 테스트를 위한 응답입니다. 금기어테스트."

    async def run_masking_test(npc_level: int, user_level: int, expected_ratio: float, desc: str):
        print(f"\n[Testing] {desc} (NPC={npc_level}, User={user_level}, Diff={npc_level - user_level})")
        
        mock_llm_result = {
            "response": mock_response_text,
            "analysis": {},
            "state": {"fish_level": npc_level}
        }
        
        mock_db_collection = AsyncMock()
        mock_db_collection.find_one = AsyncMock(return_value={"fish_level": user_level})

        with patch("app.services.chat_service.ga_agent") as mock_ga, \
             patch("app.services.chat_service.ga1_agent") as mock_ga1, \
             patch("app.services.chat_service.llm_engine") as mock_llm, \
             patch("app.services.chat_service.word_masker.mask_randomly", return_value="Random Masked") as mock_mask_randomly, \
             patch("app.services.chat_service.word_masker.mask_text", return_value=mock_response_text) as mock_mask_text:
             
            mock_ga.validate_input = AsyncMock(return_value=(True, message))
            mock_ga1.check_safety = AsyncMock(return_value=(True, message))
            mock_llm.ask = AsyncMock(return_value=mock_llm_result)
            mock_ga.validate_output = AsyncMock(side_effect=lambda x: (True, x))
            chat_service.db = MagicMock()
            chat_service.db.__getitem__.return_value = mock_db_collection

            result = await chat_service.process_chat_flow(user_id, npc_id, message)
            
            level_diff = npc_level - user_level
            
            # Check mask_randomly ratio
            if expected_ratio is not None:
                mock_mask_randomly.assert_called_once_with(mock_response_text, ratio=expected_ratio)
                print(f"✅ mask_randomly called exactly once with ratio={expected_ratio}")
            else:
                mock_mask_randomly.assert_not_called()
                print(f"✅ mask_randomly was NOT called")
                
            # Check mask_text invocation
            if level_diff >= 2 or npc_level >= 3:
                mock_mask_text.assert_called_once_with(mock_response_text)
                print(f"✅ mask_text called (level_diff={level_diff}, npc_level={npc_level})")
            else:
                mock_mask_text.assert_not_called()
                print(f"✅ mask_text NOT called (level_diff={level_diff}, npc_level={npc_level})")

    # [Test Cases]
    # 1. Diff = 3: Ratio 0.8
    await run_masking_test(npc_level=4, user_level=1, expected_ratio=0.8, desc="Diff >= 3")
    
    # 2. Diff = 2: Ratio 0.6
    await run_masking_test(npc_level=3, user_level=1, expected_ratio=0.6, desc="Diff == 2")
    
    # 3. Diff = 1: Ratio 0.2
    await run_masking_test(npc_level=2, user_level=1, expected_ratio=0.2, desc="Diff == 1")
    
    # 4. Diff = 0 (npc_level < 3): No Ratio
    await run_masking_test(npc_level=2, user_level=2, expected_ratio=None, desc="Diff == 0 (Low NPC Level)")

    # 5. Diff = 0 (npc_level >= 3): No Ratio, But mask_text should be called
    await run_masking_test(npc_level=3, user_level=3, expected_ratio=None, desc="Diff == 0 (High NPC Level)")

    print("\n🎉 All Masking Strategy Tests Passed!")

if __name__ == "__main__":
    try:
        asyncio.run(test_fish_level_masking())
        os._exit(0)
    except AssertionError as e:
        print(f"\n❌ Test Failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
        sys.exit(1)
