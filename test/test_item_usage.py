import asyncio
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.chat_service import chat_service
from app.services.inventory_service import inventory_service
from app.data.init_data import init_items

async def test_item_usage():
    print("=== Item Usage in Chat Test ===")

    # 1. Test Data Initialization
    print("\n[Step 1] Testing Data Initialization...")
    
    # Mock DB for init_items
    with patch("app.data.init_data.db", MagicMock()) as mock_db:
        mock_collection = AsyncMock()
        mock_db.__getitem__.return_value = mock_collection
        
        # Run init_items
        await init_items()
        
        # Verify update_one was called (checking if items were processed)
        assert mock_collection.update_one.called, "DB update_one should be called"
        print("✅ Data Initialization Logic Verified")

    # 2. Test Item Usage Logic in ChatService
    print("\n[Step 2] Testing ChatService Logic with Item...")
    
    user_id = "test_user"
    npc_id = "test_npc"
    item_id = "item001"
    message = "Hello"
    
    # Mock InventoryService methods
    inventory_service.check_item_ownership = AsyncMock(return_value=True)
    inventory_service.get_item_info = AsyncMock(return_value={
        "name": "Smart Phone", 
        "consumable": False
    })
    inventory_service.use_item = AsyncMock()
    
    # Mock LLM Engine and Guardrails
    with patch("app.services.chat_service.llm_engine") as mock_llm, \
         patch("app.services.chat_service.ga_agent") as mock_ga, \
         patch("app.services.chat_service.ga1_agent") as mock_ga1:
        
        # Setup mocks to pass guardrails
        mock_llm.ask = AsyncMock(return_value={"response": "Hi", "state": {}})
        mock_ga.validate_input = AsyncMock(return_value=(True, "Safe"))
        mock_ga.validate_output = AsyncMock(return_value=(True, "Safe Output")) # Added this
        mock_ga1.check_safety = AsyncMock(return_value=(True, "Safe"))
        
        # Mock other dependencies
        chat_service.handle_troll_event = AsyncMock(return_value=False)
        chat_service._get_recent_history = AsyncMock(return_value=[])
        
        # Call process_chat_flow
        await chat_service.process_chat_flow(user_id, npc_id, message, item_id)
        
        # Verify LLM was called with injected prompt
        args, _ = mock_llm.ask.call_args
        sent_message = args[1] # Check the message argument
        print(f"Sent Message to LLM: {sent_message}")
        
        assert "[System] User uses item: Smart Phone" in sent_message, "Item usage prompt should be injected"
        print("✅ Prompt Injection Verified")

    # 3. Test Consumable Item
    print("\n[Step 3] Testing Consumable Item...")
    inventory_service.get_item_info = AsyncMock(return_value={
        "name": "Potion", 
        "consumable": True
    })
    
    with patch("app.services.chat_service.llm_engine") as mock_llm, \
         patch("app.services.chat_service.ga_agent") as mock_ga, \
         patch("app.services.chat_service.ga1_agent") as mock_ga1:
        
        mock_llm.ask = AsyncMock(return_value={"response": "Gulp", "state": {}})
        mock_ga.validate_input = AsyncMock(return_value=(True, "Safe"))
        mock_ga.validate_output = AsyncMock(return_value=(True, "Safe Output")) # Added this
        mock_ga1.check_safety = AsyncMock(return_value=(True, "Safe"))
        
        await chat_service.process_chat_flow(user_id, npc_id, message, "item_potion")
        
        assert inventory_service.use_item.called, "use_item should be called for consumable"
        print("✅ Consumable Item Logic Verified")

    print("\n🎉 All Item Usage Tests Passed!")

if __name__ == "__main__":
    try:
        asyncio.run(test_item_usage())
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
