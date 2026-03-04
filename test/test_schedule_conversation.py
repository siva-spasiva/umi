import asyncio
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock dependencies before import
sys.modules["dotenv"] = MagicMock()
sys.modules["app.core.config"] = MagicMock()
sys.modules["app.agents.llm_engine"] = MagicMock()
# sys.modules["app.core.memory.memory_manager"] = MagicMock() # OLD
sys.modules["app.core.memory"] = MagicMock() # NEW: Mock the module
# We need memory_manager instance inside it
sys.modules["app.core.memory"].memory_manager = MagicMock()

# Now import service (it will use mocked modules)
# But wait, conversation_service imports llm_engine at top level.
# If we mock llm_engine, we need to ensure conversation_service can still be imported.
# Actually, conversation_service.py has:
# from app.agents.llm_engine import llm_engine
# So if sys.modules["app.agents.llm_engine"] exists, it will try to get llm_engine attribute.

mock_llm_engine_module = MagicMock()
sys.modules["app.agents.llm_engine"] = mock_llm_engine_module

# Also mock langsmith
sys.modules["langsmith"] = MagicMock()

from app.services.conversation_service import conversation_service
# Mock pydantic if needed (though schemas use it)
sys.modules["pydantic"] = MagicMock()

# Mock app.schemas.conversation
mock_schema_module = MagicMock()
sys.modules["app.schemas.conversation"] = mock_schema_module

# Define Dummy ConversationResponse
class ConversationResponse:
    def __init__(self, topic, turns, npc_states):
        self.topic = topic
        self.turns = turns
        self.npc_states = npc_states

mock_schema_module.ConversationResponse = ConversationResponse

from app.services.conversation_service import conversation_service

async def test_schedule_trigger():
    print("=== Schedule Trigger Verification ===")
    
    # Test Case: Day 3, Afternoon
    # Expectation: npc_a (Default: Chapel) and bingeo (Day 3: Chapel) overlap.
    day_index = 3
    session = "afternoon"
    
    print(f"Triggering for Day {day_index} {session}...")
    
    # Mock LLM generation to avoid real API/GPU calls
    # We mock conversation_service.start_auto_conversation or llm_engine.ask
    # Let's mock start_auto_conversation to return a dummy response
    
    mock_response = ConversationResponse(
        topic="Chapel Chat",
        turns=[],
        npc_states={}
    )
    
    # Mock StoryAgent
    sys.modules["app.agents.story_agent"] = MagicMock()
    from app.agents.story_agent import story_agent
    
    # Mock StoryAgent.summarize_event
    story_agent.summarize_event = MagicMock(return_value="[Summary] NPC A and Bingeo met at the Chapel.")
    
    # Configure mocks
    mock_memory_manager = sys.modules["app.core.memory"].memory_manager
    mock_add_memory = mock_memory_manager.add_memory
    
    with patch.object(conversation_service, "start_auto_conversation", new_callable=AsyncMock) as mock_start:
        mock_start.return_value = mock_response
        
        results = await conversation_service.trigger_scheduled_conversations(day_index, session)
        
        print(f"Results count: {len(results)}")
        
        if len(results) > 0:
            print("✅ Conversation triggered!")
            
            # Check arguments passed to start_auto_conversation
            args = mock_start.call_args
            npc_ids = args.kwargs.get('npc_ids')
            print(f"  Participants: {npc_ids}")
            
            # Verify Memory Save (Check call on the mock object directly)
            mock_add_memory.assert_called_once()
            mem_args = mock_add_memory.call_args
            print(f"  Memory Saved: {mem_args}")
            
            added_text = mem_args[1]['text']
            added_meta = mem_args[1]['metadata']
            
            assert "[Summary]" in added_text
            assert added_meta['memory_type'] == "scheduled_event"
            assert "full_log" in added_meta
            
            print("  - Summary used as memory text ✔️")
            print("  - Full log saved in metadata ✔️")
            
            story_agent.summarize_event.assert_called_once()
            print("  - StoryAgent.summarize_event called ✔️")
        else:
            # ... (debug print)
            import json
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            with open(os.path.join(base_dir, "data", "schedule.json"), "r") as f:
                data = json.load(f)
                print(f"DEBUG: npc_a day 3 afternoon: {data['JEONGGWANGEO']['default']['afternoon']}")
                print(f"DEBUG: bingeo day 3 afternoon: {data['bingeo']['3']['afternoon']}")

if __name__ == "__main__":
    try:
        asyncio.run(test_schedule_trigger())
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
