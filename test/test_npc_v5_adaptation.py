import os
import sys
import asyncio
from unittest.mock import AsyncMock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 테스트 종료 시 LangSmith 백그라운드 스레드 예외 방지
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

from app.agents.npc_dialogue_engine import sanitize_npc_response
from app.services.conversation_service import conversation_service


def test_sanitize_v5_markers():
    raw = """
### 출력
[NPC] 안녕! 오늘은 조용하네.
SAY: 이 아래는 노출되면 안 됨
Player's choice: ...
"""
    cleaned = sanitize_npc_response(raw)
    assert "SAY:" not in cleaned
    assert "Player's choice" not in cleaned
    assert "안녕! 오늘은 조용하네." in cleaned
    print("✅ sanitize_npc_response v5 marker cut 동작")


async def test_npc_only_rule_and_player_ref_block():
    import app.services.conversation_service as conv_module
    original_ask = conv_module.llm_engine.ask

    try:
        conv_module.llm_engine.ask = AsyncMock(return_value={
            "response": "그 사람(플레이어) 얘기 들었어?",
            "analysis": {"reason_tags": [], "friendly_delta": 0, "faith_delta": 0},
            "state": {"friendly": 60, "faith": 60},
        })

        resp = await conversation_service.start_auto_conversation(
            topic="식당 분위기",
            npc_ids=["bingeo", "galchi"],
            num_turns=1
        )
        assert len(resp.turns) == 1
        assert "플레이어" not in resp.turns[0].content
        assert "주제" in resp.turns[0].content
        print("✅ NPC↔NPC 플레이어 언급 억제 동작")
    finally:
        conv_module.llm_engine.ask = original_ask


if __name__ == "__main__":
    test_sanitize_v5_markers()
    asyncio.run(test_npc_only_rule_and_player_ref_block())
