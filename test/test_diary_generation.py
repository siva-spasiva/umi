import asyncio
import sys
import os
import json
from unittest.mock import AsyncMock, patch, MagicMock

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.chat_service import chat_service
from app.agents.story_agent import story_agent
from app.schemas.story import StorySummary

async def test_diary_generation():
    print("=== Server-side Diary Generation Test ===")

    user_id = "test_user_diary_gen"
    day_index = 1
    
    # Mock Chat Logs (Cult Theme: 'Mother Ocean')
    # Scenario: User talks to 3 NPCs (approx 7 turns each) about the village's strange secret.
    mock_logs = []
    
    # NPC 1: GwakBingeo (Fanatic)
    mock_logs.extend([
        {"speaker": "user", "content": "이 마을 사람들, 다들 눈이 왜 그래요?"},
        {"speaker": "GwakBingeo", "content": "어머니 바다의 축복을 받아서 그래. 너도 곧 알게 될 거야."},
        {"speaker": "user", "content": "어머니 바다? 그게 무슨 소리입니까?"},
        {"speaker": "GwakBingeo", "content": "깊고 어두운 곳에서 우릴 지켜보시는 분이지. 거역하면 안 돼."},
        {"speaker": "user", "content": "사이비 종교 같은 건가요? 신고해야겠네."},
        {"speaker": "GwakBingeo", "content": "신고? 하하하. 여기서 나갈 수 있다고 생각해? 바다는 어디에나 있어."},
        {"speaker": "user", "content": "말이 안 통하네. 비켜요."}
    ])
    
    # NPC 2: CheongGalchi (Suspicious Merchant)
    mock_logs.extend([
        {"speaker": "user", "content": "여기 물건들은 다 젖어있네요. 왜 이런 거죠?"},
        {"speaker": "CheongGalchi", "content": "물기는 생명의 근원이야. 이 '성수'를 좀 사시겠나?"},
        {"speaker": "user", "content": "그냥 바닷물 아니에요? 냄새나는데."},
        {"speaker": "CheongGalchi", "content": "무례하군! 이건 어머니의 눈물이다. 마시면 진실이 보여."},
        {"speaker": "user", "content": "됐습니다. 혹시 나가는 길은 압니까?"},
        {"speaker": "CheongGalchi", "content": "들어올 땐 마음대로였지만... 제물은 함부로 못 나가지."},
        {"speaker": "user", "content": "제물? 지금 날 제물 취급하는 거야?"}
    ])
    
    # NPC 3: JeongGwangeo (Village Chief / Cult Leader)
    mock_logs.extend([
        {"speaker": "System", "content": "[System] User uses item: Flashlight"},
        {"speaker": "user", "content": "당신이 촌장인가? 마을 분위기가 왜 이래?"},
        {"speaker": "JeongGwangeo", "content": "손님, 너무 밝은 빛은 좋지 않습니다. 심해의 아이들은 빛을 싫어하죠."},
        {"speaker": "user", "content": "숨기는 게 뭐지? 지하 창고에서 이상한 소리가 들리던데."},
        {"speaker": "JeongGwangeo", "content": "그건... 축복의 노래입니다. 오늘 밤 의식이 있을 겁니다."},
        {"speaker": "user", "content": "의식? 사람이라도 해치는 건가?"},
        {"speaker": "JeongGwangeo", "content": "해치는 게 아닙니다. 하나가 되는 것이지. 당신도 초대합니다."},
        {"speaker": "user", "content": "미친 소리. 난 빠지겠어."}
    ])
    
    # Mock LLM Response (JSON) - Reflecting the Cult Theme
    mock_llm_json = {
        "day_index": day_index,
        "diary": {
            "title": "광기에 물든 마을",
            "text": "이 마을은 미쳤다. 주민들은 '어머니 바다'라는 존재를 맹신하고 있다. 곽빙어와 청갈치는 나를 제물 취급하며 알 수 없는 소리를 지껄였다. 촌장 정광어는 오늘 밤 '의식'이 있다고 했다. 탈출구를 찾아야 한다.",
            "tone": "fearful"
        },
        "summary_bullets": [
            "주민들이 '어머니 바다'라는 사이비 신앙을 가지고 있음",
            "청갈치가 '성수'를 권하며 주인공을 제물로 언급함",
            "촌장이 오늘 밤 지하 창고에서 의식이 있다고 예고함"
        ],
        "key_conversations": [
            {"with": "GwakBingeo", "what_changed": "마을의 광적인 신앙 확인", "quote": "여기서 나갈 수 있다고 생각해? 바다는 어디에나 있어."},
            {"with": "CheongGalchi", "what_changed": "자신이 제물임을 인지", "quote": "들어올 땐 마음대로였지만... 제물은 함부로 못 나가지."},
            {"with": "JeongGwangeo", "what_changed": "의식의 존재 확인", "quote": "그건... 축복의 노래입니다. 오늘 밤 의식이 있을 겁니다."}
        ],
        "items": [
            {"name": "Flashlight", "how_used_or_implication": "촌장 앞에서 사용했으나, 빛을 싫어한다는 경고를 들음"}
        ],
        "clues": [
            {"info": "오늘 밤 지하 창고에서 의식이 열린다", "importance": "high"},
            {"info": "마을 사람들은 외부인을 제물로 본다", "importance": "high"}
        ],
        "troll_level_analysis": {
            "delta_total": 0,
            "top_causes": []
        },
        "consistency_check": {
            "contradictions_found": [],
            "missing_info": ["탈출구의 위치"]
        },
        "ending": {
            "status": "continue",
            "ending_type": "null",
            "reason": "",
            "required_next_step": "avoid_ritual"
        },
        "flags_for_next_day": [
            {"flag": "night_ritual_event", "why": "Chief mentioned a ritual tonight"}
        ],
        "safety": {
            "hallucination_risk": "mid",
            "spoiler_blocked": False
        }
    }
    
    print("\n[Step 1] Mocking DB and LLM...")
    
    # Patch dependencies
    with patch.object(chat_service, "_get_recent_history", return_value=mock_logs) as mock_history, \
         patch.object(story_agent, "generate", return_value=json.dumps(mock_llm_json)) as mock_llm, \
         patch.object(chat_service, "save_story_summary", new_callable=AsyncMock) as mock_save:
             
        print("\n[Step 2] Calling create_diary_entry...")
        result = await chat_service.create_diary_entry(user_id, day_index)
        
        print("\n[Step 3] Verification")
        print(f"  - Result type: {type(result)}")
        print(f"  - Diary Title: {result.diary.title}")
        print(f"  - Diary Text: {result.diary.text}")
        print(f"  - Clues Found: {len(result.clues)}")
        
        # Assertions
        assert isinstance(result, StorySummary)
        assert result.diary.title == "광기에 물든 마을"
        assert len(result.clues) >= 1
        assert "Flashlight" in str(result.items)
        
        # Check LLM call arguments (Prompt check)
        call_args = mock_llm.call_args[0][0]
        print(f"\n[Step 4] Prompt Inspection (Snippet):")
        # Print a chunk of the prompt to verify logs are included
        start_idx = call_args.find("Logs:")
        print(call_args[start_idx:start_idx+500] + "...")
        
        if "어머니 바다" in call_args:
             print("  ✅ Prompt contains cult theme content")
        else:
             print("  ❌ Prompt content check failed")

        print("\n✅ Test Passed!")

if __name__ == "__main__":
    asyncio.run(test_diary_generation())
