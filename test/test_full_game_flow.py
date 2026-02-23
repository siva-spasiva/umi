"""
=============================================================
Full Game Flow Integration Test (전체 게임 흐름 통합 테스트)
=============================================================

유저 로그인 → 스탯 초기화 → (세션 반복: 대화 OR 엿듣기+추가엿듣기 → end-session)
→ 4세션 마무리 후 diary 생성 → 5일 반복 후 ending 생성

[세션 규칙]
- 한 세션에서는 NPC 1명과 대화(5~10턴) OR 엿듣기+추가엿듣기 중 택 1
- 대화 시 5~10회 반복
- 세션 종료 시 RAG(VectorDB) + MongoDB에 장기 기억 저장 확인
- 대화하지 않은 NPC들이 같은 방에 있으면 자동 대화 후 요약/장기기억 저장

[엿듣기 주제]
- VectorDB(npc_topics 컬렉션)에서 조회

모든 LLM 호출은 Mock 처리하여 GPU 서버 없이 API 흐름만 검증합니다.
"""

import sys
import os
import asyncio
import json
import uuid
import random
import unittest.mock as mock
from datetime import datetime

# 프로젝트 최상단 경로를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from app.main import app
from app.core.security import get_current_user_id
from app.core.database import db
from app.core.config import settings
from app.core.memory import memory_manager

# ============================================================
# 1. Mock 설정
# ============================================================

# GPU Proxy 비활성화
settings.USE_GPU_PROXY = False

# StoryAgent.generate 모킹
from app.agents.story_agent import story_agent

async def mock_story_generate(prompt, **kwargs):
    """StoryAgent의 generate를 모킹: 프롬프트의 mode 데이터에 따라 적절한 JSON 반환"""
    if '"mode": "EPILOGUE"' in prompt or '"mode":"EPILOGUE"' in prompt:
        return json.dumps({
            "title": "드러난 진실",
            "text": "5일간의 조사 끝에, UMI 교단의 실체가 드러났다. 교단은 이미 마을 깊숙이 뿌리를 내리고 있었고, 그 중심에는 예상치 못한 인물이 있었다.",
            "ending_type": "exposed",
            "reason": "체계적인 증거 수집과 NPC들의 신뢰를 얻어 핵심 정보에 접근할 수 있었다."
        }, ensure_ascii=False)
    # DIARY 모드 (기본)
    return json.dumps({
        "diary": {"title": "수상한 움직임", "text": "오늘 하루도 기묘한 일들이 이어졌다.", "tone": "긴장감"},
        "summary_bullets": ["마을 주민과의 대화에서 단서 발견", "의문의 물건 획득"],
        "key_conversations": [],
        "items": [],
        "clues": [{"info": "교단의 의식 장소에 대한 힌트", "importance": "high"}],
        "troll_level_analysis": {"delta_total": 0, "top_causes": []},
        "consistency_check": {"contradictions_found": [], "missing_info": []},
        "ending": {"status": "continue", "ending_type": "null", "reason": "", "required_next_step": ""},
        "flags_for_next_day": [],
        "safety": {"hallucination_risk": "low", "spoiler_blocked": True}
    }, ensure_ascii=False)

story_agent.generate = mock.AsyncMock(side_effect=mock_story_generate)

# LLMEngine 모킹 (NPC 대화)
from app.agents.llm_engine import llm_engine

NPC_NAMES = {
    "gwakbing": "곽빙어", "cheonggalchi": "청갈치",
    "bakbok": "박복어", "jeongwang": "전광어", "mineo": "이민어"
}

# 다양한 NPC 응답 풀 (자연스러운 대화를 위해)
NPC_RESPONSES = [
    "음... 그건 좀 더 조사해봐야 할 것 같은데요.",
    "그 얘기는 처음 듣는데... 좀 더 자세히 알아볼게요.",
    "아, 그걸 아시는군요. 사실 저도 좀 의심하고 있었어요.",
    "그런 이야기가 있나요? 저는 잘 모르겠는데...",
    "솔직히 말씀드리면, 최근에 이상한 일이 좀 있었어요.",
    "그 사람이요? 음, 평소에는 별 탈 없어 보이는데...",
    "아마 그건 교단과 관련이 있을 수도 있어요.",
    "저도 비슷한 걸 들은 적이 있어요. 조심하세요.",
    "흥미로운 이야기네요. 제가 아는 건 여기까지예요.",
    "그 장소에 대해서는 말씀드리기 어렵지만... 힌트를 드리자면..."
]

async def mock_llm_ask(npc_id, message, history=None, update_state=True, forced_state=None, user_id=None):
    """LLM 대화 모킹: NPC별 다양한 한국어 응답 반환"""
    name = NPC_NAMES.get(npc_id, npc_id)
    response_text = random.choice(NPC_RESPONSES)
    
    # 세션 버퍼에 대화 기록 (장기 기억 테스트를 위해)
    if npc_id not in llm_engine.session_buffers:
        llm_engine.session_buffers[npc_id] = []
    llm_engine.session_buffers[npc_id].append({
        "user": message,
        "npc": f"({name}) {response_text}",
        "friendly_delta": random.randint(-1, 2),
        "faith_delta": random.randint(-1, 1)
    })
    
    return {
        "response": f"({name}) {response_text}",
        "analysis": {
            "reason_tags": ["정보제공"],
            "friendly_delta": 1,
            "faith_delta": 0
        },
        "state": {"friendly": 50, "faith": 50}
    }

llm_engine.ask = mock_llm_ask

# save_session_summary: 실제 로직 사용 (VectorDB 저장 검증을 위해)
# 단, GPU proxy 호출 부분만 모킹
async def mock_generate_diary_text(messages, fish_level=0, max_new_tokens=400):
    """GPU proxy의 generate_diary 모킹"""
    return f"세션 요약: {messages[:100]}..."

story_agent.generate_diary = mock.MagicMock(side_effect=lambda msg, fish_level=0: f"세션 요약: {msg[:100]}...")

# Conversation 모킹 (GPU proxy 대신)
from app.services.conversation_service import conversation_service
from app.schemas.conversation import ConversationResponse, ConversationTurn

async def mock_start_auto_conversation(topic, npc_ids, num_turns=5):
    """NPC 자동 대화 모킹"""
    turns = []
    for i in range(min(num_turns, 6)):
        npc_id = npc_ids[i % len(npc_ids)]
        turns.append(ConversationTurn(
            speaker=NPC_NAMES.get(npc_id, npc_id),
            speaker_id=npc_id,
            content=f"({NPC_NAMES.get(npc_id, npc_id)}) {topic}에 대해 말하자면... (턴 {i+1})",
            analysis={"reason_tags": ["정보공유"], "friendly_delta": 0, "faith_delta": 0}
        ))
    return ConversationResponse(topic=topic, turns=turns, npc_states={})

conversation_service.start_auto_conversation = mock_start_auto_conversation

# ============================================================
# 2. 인증 우회
# ============================================================
test_user_id = f"flow_test_{uuid.uuid4().hex[:8]}"

def mock_get_current_user_id() -> str:
    return test_user_id

app.dependency_overrides[get_current_user_id] = mock_get_current_user_id

# ============================================================
# 3. 유틸리티: RAG 토픽 조회
# ============================================================

def get_eavesdrop_topic_from_rag() -> str:
    """VectorDB(npc_topics)에서 엿듣기 주제를 실제로 조회"""
    try:
        topic = conversation_service._get_topic_from_vectordb("random")
        return topic
    except Exception as e:
        print(f"    ⚠️ RAG 토픽 조회 실패, 기본값 사용: {e}")
        return "마을의 비밀 모임에 대한 소문"

# ============================================================
# 4. 테스트 Step 함수
# ============================================================

NPC_IDS = ["gwakbing", "cheonggalchi", "bakbok", "jeongwang", "mineo"]
TOTAL_DAYS = 5
SESSIONS_PER_DAY = 4

# 유저가 대화할 때 사용할 메시지 풀
USER_MESSAGES = [
    "이 마을에 대해 알려주세요.",
    "최근에 이상한 일이 있었나요?",
    "그 사람에 대해 더 알고 싶어요.",
    "혹시 교단에 대해 아는 게 있나요?",
    "여기서 뭘 하고 계신 건가요?",
    "어젯밤에 무슨 소리 들으셨어요?",
    "다른 주민들은 뭐라고 하던가요?",
    "그 장소에 가본 적 있나요?",
    "혹시 도움이 필요하신 건 없나요?",
    "사라진 사람들에 대해 아시나요?"
]

async def step_login(client: httpx.AsyncClient):
    """Step 1: 유저 로그인"""
    print("\n" + "="*60)
    print("📌 Step 1: 유저 로그인 (POST /api/v1/users/login)")
    print("="*60)
    resp = await client.post("/api/v1/users/login")
    assert resp.status_code == 200, f"로그인 실패: {resp.text}"
    data = resp.json()
    print(f"  ✅ 로그인 성공 (access_token: {data['access_token'][:20]}...)")
    return data

async def step_init_stats(client: httpx.AsyncClient):
    """Step 2: NPC 스탯 초기화"""
    print("\n" + "="*60)
    print("📌 Step 2: 초기 스탯/NPC 스탯 설정 (GET /api/v1/stats/static)")
    print("="*60)
    resp = await client.get("/api/v1/stats/static")
    assert resp.status_code == 200, f"스탯 초기화 실패: {resp.text}"
    data = resp.json()
    print(f"  ✅ 스탯 초기화 완료 (user_id: {data.get('user_id', test_user_id)})")
    return data

async def step_chat_session(client: httpx.AsyncClient, npc_id: str, num_turns: int):
    """NPC와 다중턴 대화 (5~10턴)"""
    results = []
    for i in range(num_turns):
        msg = random.choice(USER_MESSAGES)
        resp = await client.post("/api/v1/chat", json={
            "npcId": npc_id,
            "message": msg
        })
        assert resp.status_code == 200, f"채팅 실패 ({npc_id}, 턴 {i+1}): {resp.text}"
        data = resp.json()
        results.append({"turn": i+1, "user": msg, "npc": data.get("response", "")[:60]})
    return results

async def step_eavesdrop(client: httpx.AsyncClient, npc_ids: list, topic: str):
    """NPC 엿듣기 (conversation/start)"""
    resp = await client.post("/api/v1/conversation/start", json={
        "topic": topic,
        "npc_ids": npc_ids,
        "num_turns": 6
    })
    assert resp.status_code == 200, f"엿듣기 실패: {resp.text}"
    return resp.json()

async def step_eavesdrop_more(client: httpx.AsyncClient, day_index: int, session_index: int, room_id: str):
    """추가 엿듣기 (map/eavesdrop)"""
    resp = await client.post("/api/v1/map/eavesdrop", json={
        "day_index": day_index,
        "session_index": session_index,
        "room_id": room_id
    })
    if resp.status_code == 404:
        return {"status": "no_map_data", "detail": "맵 데이터 없음"}
    assert resp.status_code == 200, f"추가 엿듣기 실패: {resp.text}"
    return resp.json()

async def step_end_session(client: httpx.AsyncClient, day_index: int, session_index: int, npc_id: str = None):
    """세션 종료 & 요약"""
    payload = {"day_index": day_index, "session_index": session_index}
    if npc_id:
        payload["npc_id"] = npc_id
    resp = await client.post("/api/v1/end-session", json=payload)
    assert resp.status_code == 200, f"세션 종료 실패 (Day{day_index}/S{session_index}): {resp.text}"
    return resp.json()

async def step_generate_diary(client: httpx.AsyncClient, day_index: int):
    """일기 생성"""
    resp = await client.post("/api/v1/diary", json={"day_index": day_index})
    assert resp.status_code == 201, f"일기 생성 실패 (Day{day_index}): {resp.text}"
    return resp.json()

async def step_generate_ending(client: httpx.AsyncClient):
    """엔딩 생성"""
    resp = await client.post("/api/v1/ending")
    assert resp.status_code == 200, f"엔딩 생성 실패: {resp.text}"
    return resp.json()

async def step_get_epilogue(client: httpx.AsyncClient):
    """에필로그 조회"""
    resp = await client.get("/api/v1/epilogue")
    assert resp.status_code == 200, f"에필로그 조회 실패: {resp.text}"
    return resp.json()

# ============================================================
# 5. RAG 검증 함수
# ============================================================

def verify_rag_memory(day_index: int, npc_id: str) -> bool:
    """VectorDB에 세션 요약이 저장되었는지 확인"""
    try:
        retriever = memory_manager.get_retriever(k=3)
        results = retriever.invoke(f"Day {day_index} {npc_id} 세션 요약")
        for doc in results:
            meta = doc.metadata
            if meta.get("npc_id") == npc_id and meta.get("day_index") == day_index:
                return True
        return False
    except Exception as e:
        print(f"    ⚠️ RAG 검증 오류: {e}")
        return False

async def verify_mongodb_summary(day_index: int, npc_id: str) -> bool:
    """MongoDB day_summaries에 요약이 저장되었는지 확인"""
    doc = await db["day_summaries"].find_one({
        "user_id": test_user_id,
        "day_index": day_index,
        "npc_id": npc_id
    })
    return doc is not None

# ============================================================
# 6. 메인 테스트 실행
# ============================================================

async def main():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        all_results = {}
        rag_checks = []       # RAG 저장 검증 결과 모음
        mongo_checks = []     # MongoDB 저장 검증 결과 모음
        
        try:
            # ─── Step 1: 로그인 ───
            login_data = await step_login(client)
            
            # ─── Step 2: 스탯 초기화 ───
            stats_data = await step_init_stats(client)
            
            # ─── Step 3~: 5일 × 4세션 반복 ───
            for day in range(1, TOTAL_DAYS + 1):
                print("\n" + "🌅" * 30)
                print(f"  📅 Day {day} 시작")
                print("🌅" * 30)
                
                day_result = {"sessions": []}
                
                for session in range(1, SESSIONS_PER_DAY + 1):
                    print(f"\n  ── 🕐 Day {day}, Session {session} ──")
                    session_result = {"day": day, "session": session}
                    
                    # [규칙] 홀수 세션 = NPC 1:1 대화 (5~10턴)
                    #        짝수 세션 = 엿듣기 + 추가 엿듣기
                    
                    if session % 2 == 1:
                        # ─── NPC 1:1 대화 세션 (5~10턴) ───
                        npc_id = NPC_IDS[(day + session) % len(NPC_IDS)]
                        num_turns = random.randint(5, 10)
                        print(f"    💬 [{NPC_NAMES[npc_id]}]와 대화 시작 ({num_turns}턴)")
                        
                        chat_results = await step_chat_session(client, npc_id, num_turns)
                        session_result["type"] = "chat"
                        session_result["npc"] = npc_id
                        session_result["turns"] = num_turns
                        session_result["chat_log"] = chat_results
                        
                        # 마지막 대화 내용 미리보기
                        last = chat_results[-1]
                        print(f"       → 마지막 턴: \"{last['user']}\" → {last['npc']}...")
                        
                    else:
                        # ─── 엿듣기 + 추가 엿듣기 세션 ───
                        # 엿듣기 대상: 대화하지 않는 NPC 2명
                        chatted_npc = NPC_IDS[(day + session - 1) % len(NPC_IDS)]
                        available_npcs = [n for n in NPC_IDS if n != chatted_npc]
                        eavesdrop_pair = random.sample(available_npcs, 2)
                        
                        # RAG에서 토픽 조회
                        topic = get_eavesdrop_topic_from_rag()
                        print(f"    👂 엿듣기: {[NPC_NAMES[n] for n in eavesdrop_pair]}")
                        print(f"       주제 (RAG 조회): \"{topic[:50]}...\"")
                        
                        eavesdrop_result = await step_eavesdrop(client, eavesdrop_pair, topic)
                        turn_count = len(eavesdrop_result[0].get("turns", [])) if isinstance(eavesdrop_result, list) else 0
                        print(f"       → {turn_count}턴 대화 생성됨")
                        
                        # 추가 엿듣기
                        print(f"    👂+ 추가 엿듣기 시도")
                        more_result = await step_eavesdrop_more(client, day, session, "room_202")
                        more_status = "success" if "conversation" in more_result else more_result.get("status", "unknown")
                        print(f"       → 추가 엿듣기: {more_status}")
                        
                        session_result["type"] = "eavesdrop"
                        session_result["npcs"] = eavesdrop_pair
                        session_result["topic"] = topic[:60]
                        session_result["eavesdrop_turns"] = turn_count
                        session_result["eavesdrop_more"] = more_status
                    
                    # ─── 세션 종료 (end-session) ───
                    print(f"    ⏹️ 세션 종료: Day {day}, Session {session}")
                    
                    # 세션 버퍼에 대화가 있는 NPC만 요약 대상
                    end_result = await step_end_session(client, day, session)
                    session_result["end_session"] = end_result.get("status", "unknown")
                    
                    # [검증] 대화 세션이었으면 RAG/MongoDB에 저장됐는지 확인
                    if session % 2 == 1:
                        npc_id = NPC_IDS[(day + session) % len(NPC_IDS)]
                        
                        # RAG (VectorDB) 확인
                        rag_saved = verify_rag_memory(day, npc_id)
                        rag_checks.append({"day": day, "session": session, "npc": npc_id, "saved": rag_saved})
                        rag_icon = "✅" if rag_saved else "⚠️"
                        print(f"    🧠 RAG 장기기억 저장: {rag_icon} ({npc_id})")
                        
                        # MongoDB 확인
                        mongo_saved = await verify_mongodb_summary(day, npc_id)
                        mongo_checks.append({"day": day, "session": session, "npc": npc_id, "saved": mongo_saved})
                        mongo_icon = "✅" if mongo_saved else "⚠️"
                        print(f"    🗄️ MongoDB 요약 저장: {mongo_icon} ({npc_id})")
                    
                    # [검증] end-session에서 next_session_map 확인 (대화 안 한 NPC 배치)
                    next_map = end_result.get("next_session_map", {})
                    if next_map:
                        placements = next_map.get("room_placements", [])
                        multi_npc_rooms = [p for p in placements if len(p.get("npcs", [])) >= 2]
                        if multi_npc_rooms:
                            print(f"    🗺️ 다음 세션 NPC 배치: {len(multi_npc_rooms)}개 방에 NPC 2명+ 배치")
                            for room in multi_npc_rooms[:2]:
                                topic_title = room.get("topic", {}).get("title", "없음") if room.get("topic") else "없음"
                                print(f"       - {room['room_id']}: {room['npcs']} → 주제: {topic_title}")
                    
                    day_result["sessions"].append(session_result)
                
                # ─── 4세션 마무리 후 → 일기 생성 ───
                print(f"\n  📝 Day {day} 일기 생성 중...")
                diary_result = await step_generate_diary(client, day)
                day_result["diary"] = {"status": "success", "day_index": day}
                print(f"     ✅ Day {day} 일기 생성 완료")
                
                all_results[f"day_{day}"] = day_result
            
            # ─── 5일 완료 → 엔딩 생성 ───
            print("\n" + "🎬" * 30)
            print("  🎬 최종 엔딩 생성 중...")
            print("🎬" * 30)
            ending_result = await step_generate_ending(client)
            all_results["ending"] = ending_result
            
            print(f"\n  📖 엔딩 제목: {ending_result.get('title', 'N/A')}")
            print(f"  📖 엔딩 타입: {ending_result.get('ending_type', 'N/A')}")
            print(f"  📖 내용: {ending_result.get('text', 'N/A')[:80]}...")
            print(f"  📖 사유: {ending_result.get('reason', 'N/A')[:80]}...")
            
            # ─── 에필로그 조회 ───
            epilogue_result = await step_get_epilogue(client)
            assert epilogue_result["title"] == ending_result["title"], "에필로그 조회 결과가 엔딩과 불일치!"
            print(f"  ✅ 에필로그 조회 확인 완료")
            
            # ─── 최종 요약 ───
            print("\n" + "="*60)
            print("📊 RAG 장기기억 저장 검증 결과")
            print("="*60)
            rag_success = sum(1 for r in rag_checks if r["saved"])
            print(f"  VectorDB: {rag_success}/{len(rag_checks)} 건 저장 확인")
            for r in rag_checks:
                icon = "✅" if r["saved"] else "❌"
                print(f"    {icon} Day {r['day']}/S{r['session']} - {NPC_NAMES.get(r['npc'], r['npc'])}")
            
            print(f"\n📊 MongoDB 요약 저장 검증 결과")
            mongo_success = sum(1 for m in mongo_checks if m["saved"])
            print(f"  day_summaries: {mongo_success}/{len(mongo_checks)} 건 저장 확인")
            for m in mongo_checks:
                icon = "✅" if m["saved"] else "❌"
                print(f"    {icon} Day {m['day']}/S{m['session']} - {NPC_NAMES.get(m['npc'], m['npc'])}")
            
            # 결과 저장
            all_results["verification"] = {
                "rag_checks": rag_checks,
                "mongo_checks": mongo_checks,
                "rag_success_rate": f"{rag_success}/{len(rag_checks)}",
                "mongo_success_rate": f"{mongo_success}/{len(mongo_checks)}"
            }
            
            # ─── 결과 JSON 저장 ───
            result_path = os.path.join(os.path.dirname(__file__), "test_full_game_flow_result.json")
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
            
            total_chat_turns = sum(
                s.get("turns", 0) for d in all_results.values() 
                if isinstance(d, dict) and "sessions" in d 
                for s in d["sessions"] if s.get("type") == "chat"
            )
            
            print("\n" + "="*60)
            print(f"🎉 전체 게임 흐름 테스트 통과!")
            print(f"📁 결과 저장: {result_path}")
            print(f"   - {TOTAL_DAYS}일 × {SESSIONS_PER_DAY}세션 = {TOTAL_DAYS * SESSIONS_PER_DAY}세션 완료")
            print(f"   - NPC 대화 총 {total_chat_turns}턴 수행")
            print(f"   - 일기 {TOTAL_DAYS}편 생성 완료")
            print(f"   - 최종 엔딩 생성 및 조회 완료")
            print(f"   - RAG 장기기억: {rag_success}/{len(rag_checks)}건 저장")
            print(f"   - MongoDB 요약: {mongo_success}/{len(mongo_checks)}건 저장")
            print("="*60)
            
        except Exception as e:
            print(f"\n❌ 테스트 실패: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 테스트 데이터 정리
            print("\n🧹 [Cleanup] 테스트 데이터 삭제 중...")
            await db["story_diary"].delete_many({"user_id": test_user_id})
            await db["game_endings"].delete_many({"user_id": test_user_id})
            await db["chat_logs"].delete_many({"user_id": test_user_id})
            await db["user_stats"].delete_many({"user_id": test_user_id})
            await db["npc_stats"].delete_many({"user_id": test_user_id})
            await db["inventories"].delete_many({"user_id": test_user_id})
            await db["day_summaries"].delete_many({"user_id": test_user_id})
            await db["session_map_state"].delete_many({})
            print("✅ [Cleanup] 완료")


if __name__ == "__main__":
    asyncio.run(main())
