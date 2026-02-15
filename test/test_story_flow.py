import sys
import os
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings

# Force GPU Proxy mode for testing logic path
settings.USE_GPU_PROXY = True

# Mocking the GPU Proxy before importing LLMEngine to avoid connection errors if it initializes on import
sys.modules["app.core.gpu_proxy"] = MagicMock()
from app.core.gpu_proxy import gpu_proxy

# Now import the engine
from app.agents.llm_engine import llm_engine
from app.core.memory import memory_manager

# Configuration
NPC_IDS = ["JEONGGWANGEO", "CHEONGGALCHI", "REPORTER_LEE"]
DAYS = 3
TURNS_PER_DAY = 5

async def mock_generate_npc_response(npc_id, message, history=None, memory_context=None):
    """Mock response from GPU Server for NPC chat"""
    print(f"  [MockGPU] Generating response for {npc_id}...")
    if memory_context:
        print(f"  [MockGPU] Received RAG Context: {len(memory_context)} chars")
    
    return {
        "response": f"Mock response from {npc_id} to '{message}'",
        "analysis": {
            "friendly_delta": 1,
            "faith_delta": 0,
            "reason_tags": ["mock_tag"]
        },
        "state": {"friendly": 50, "faith": 50}
    }

async def mock_generate_diary(messages, fish_level=0, max_new_tokens=400):
    """Mock response from GPU Server for Diary/Summary generation"""
    print(f"  [MockGPU] Generating diary for {len(messages)} chars of conversation...")
    return f"Mock Diary Summary: User talked about '{messages[:20]}...'"

async def run_story_simulation():
    print("=== Starting 3-Day Story Simulation ===\n")

    # Setup Mocks
    gpu_proxy.generate_npc_response = AsyncMock(side_effect=mock_generate_npc_response)
    gpu_proxy.generate_diary = AsyncMock(side_effect=mock_generate_diary)

    for day in range(1, DAYS + 1):
        print(f"\n--- Day {day} Starts ---\n")
        
        for npc_id in NPC_IDS:
            print(f"\n[NPC: {npc_id}]")
            
            # Simulate 5 turns
            for turn in range(1, TURNS_PER_DAY + 1):
                user_msg = f"Day {day} Turn {turn} message to {npc_id}"
                print(f"  User: {user_msg}")
                
                # Call LLMEngine (which will call our mock_generate_npc_response)
                response = await llm_engine.ask(npc_id, user_msg)
                
                print(f"  NPC: {response['response']}")
                
                # Basic verification of state update
                # In a real test we might check if 'friendly' changed, etc.

        print(f"\n--- Day {day} Ends: Generating Summaries ---\n")
        
        # End of Day: Generate Summaries
        summaries = await llm_engine.save_session_summary(day_index=day)
        
        print(f"Generated {len(summaries)} summaries.")
        for npc, summary in summaries.items():
            print(f"  Summary for {npc}: {summary}")
            
            # Verify it was put into Memory (retrieve it back to check)
            # We use a slight delay or just check the last added memory if possible, 
            # but here we rely on the print logs from LLMEngine for now.

    print("\n=== Simulation Complete ===")

if __name__ == "__main__":
    asyncio.run(run_story_simulation())
