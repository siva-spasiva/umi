import asyncio
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Force USE_GPU_PROXY to True before importing modules
from app.core import config
config.settings.USE_GPU_PROXY = True

from app.agents.llm_engine import llm_engine
from app.api.v1.chat import end_day, EndDayRequest

# Real NPC IDs from characters.json
NPC_IDS = ["JeongGwangeo", "ParkBokeo", "CheongGalchi", "GwakBingeo"]
# ReporterLee might not have a prompt file? Loading log showed 4 NPCs. Let's stick to loaded ones.
# Log said: Available NPCs: ['GwakBingeo', 'CheongGalchi', 'ParkBokeo', 'JeongGwangeo']

async def test_real_gpu_summary():
    print("=== Real GPU Day Summary Verification ===")
    
    user_id = f"test_user_gpu_{int(datetime.now().timestamp())}"
    day_index = 1
    
    # Generate realistic conversation history for each NPC
    print(f"\n[Step 1] Generating conversation history for {len(NPC_IDS)} NPCs...")
    
    conversation_templates = [
        ("안녕, 오늘 기분 어때?", "나쁘지 않아. 너는?"),
        ("요즘 마을 분위기가 이상하지 않아?", "글쎄, 나는 잘 모르겠어."),
        ("비밀번호 좀 알려주라.", "그건 곤란해. 알려줄 수 없어."),
        ("너 생선 좋아해?", "나는 생선이야... 무슨 소리를 하는 거야?"),
        ("미안, 농담이었어.", "괜찮아. 다음부턴 조심해줘."),
        ("내일 뭐 할 거야?", "아마도 기도를 하러 가겠지."),
        ("잘 자.", "너도 잘 자.")
    ]
    
    for npc_id in NPC_IDS:
        buffer = []
        for i, (user_msg, npc_msg) in enumerate(conversation_templates):
            buffer.append({
                "user": user_msg,
                "npc": npc_msg,
                "friendly_delta": 0,
                "faith_delta": 0,
                "tags": ["small_talk"] if i % 2 == 0 else ["question"]
            })
        llm_engine.session_buffers[npc_id] = buffer
        print(f"  - {npc_id}: {len(buffer)} turns added.")

    # 2. Mock DB (We only verify insertion, not real DB write)
    # We allow GPU Proxy to be REAL, so we DO NOT patch gpu_proxy or story_agent.
    print("\n[Step 2] Calling save_day_summary (Connecting to AWS GPU)...")
    
    # Patch the DB to capture the result
    with patch("app.agents.llm_engine.db", MagicMock()) as mock_db:
        mock_collection = AsyncMock()
        mock_db.__getitem__.return_value = mock_collection
        mock_collection.insert_one = AsyncMock()
        
        # Also patch memory_manager to avoid real ChromaDB writes if needed, but it's local so maybe fine.
        # Let's mock memory_manager to keep it clean.
        with patch("app.agents.llm_engine.memory_manager") as mock_memory:
            mock_memory.add_memory = MagicMock()
            
            # Action
            summaries = await llm_engine.save_day_summary(day_index, npc_id=None, user_id=user_id)
            
            # Verify
            print(f"\n[Step 3] Verification")
            print(f"  - Summaries generated: {len(summaries)}")
            for npc_id, summary in summaries.items():
                print(f"  > [{npc_id}] Summary length: {len(summary)} chars")
                print(f"    Preview: {summary[:100]}...")
                
            # Check DB calls
            assert mock_collection.insert_one.call_count == len(NPC_IDS), f"Should insert {len(NPC_IDS)} documents"
            
            # Verify content of one insert
            call_args = mock_collection.insert_one.call_args_list[0][0][0]
            print(f"\n  - Sample DB Document for {call_args['npc_id']}:")
            print(f"    User ID: {call_args['user_id']}")
            print(f"    Summary: {call_args['summary'][:100]}...")
            print("    Scan: Full conversation included? ", "Yes" if "full_conversation" in call_args else "No")
            
            assert call_args["user_id"] == user_id
            assert "timestamp" in call_args
            
            print("\n✅ Real GPU Summary Generation & DB Storage Logic Verified!")

if __name__ == "__main__":
    try:
        # Disable tracing
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        asyncio.run(test_real_gpu_summary())
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
