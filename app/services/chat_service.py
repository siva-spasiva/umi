from app.services.base_service import BaseService
from app.schemas.chat import DayLog
from app.schemas.story import (
    StorySummary, Diary, KeyConversation, ItemUsage, Clue,
    TrollAnalysis, ConsistencyCheck, GameEnding, NextDayFlag, SafetyCheck
)
from app.agents.ga1_agent import ga1_agent
from app.agents.ga2_context import ga2_context
from app.agents.llm_engine import llm_engine
from app.agents.guardrail import ga_agent

from langsmith import traceable

class ChatService(BaseService):
    def __init__(self):
        super().__init__()
        self.collection = self.db["chat_logs"]

    @traceable(run_type="chain", name="Chat_Flow_Pipeline")
    async def process_chat_flow(self, user_id: str, npc_id: str, message: str):
        """
        GA1 -> GA2 -> LLM -> Output Guardrail 파이프라인
        """
        # 0. Basic Guardrail: 기본 규칙 검증 (길이, 금지어 등)
        is_basic_safe, basic_msg = await ga_agent.validate_input(message)
        if not is_basic_safe:
            triggered_skip = await self.handle_troll_event(user_id, "BASIC_GUARDRAIL", basic_msg)
            if triggered_skip:
                return {
                    "response": basic_msg + "\n\n(시스템: 경고 3회 누적으로 인해 하루가 강제 종료되었습니다. 다음 날로 넘어갑니다.)",
                    "status": "blocked_by_troll_limit",
                    "force_skip": True
                }
            return {"response": basic_msg, "status": "blocked_by_guardrail"}

        # 1. GA1: 입력 안전성 검증
        is_safe, safety_msg = await ga1_agent.check_safety(message)
        if not is_safe:
            # 트롤 레벨 증가 및 체크
            triggered_skip = await self.handle_troll_event(user_id, "GA1_BLOCK", safety_msg)
            if triggered_skip:
                return {
                    "response": safety_msg + "\n\n(시스템: 경고 3회 누적으로 인해 하루가 강제 종료되었습니다. 다음 날로 넘어갑니다.)",
                    "status": "blocked_by_troll_limit",
                    "force_skip": True
                }
            return {"response": safety_msg, "status": "blocked_by_ga1"}

        # 2. GA2: 문맥 및 세계관 검증
        # TODO : 아직 GA2모델이 개발되지 않아서 사용 (History는 LLM에 전달)
        history = await self._get_recent_history(user_id, npc_id, limit=5)
        # is_context_ok, context_msg = await ga2_context.check_context(message, history)
        # if not is_context_ok:
        #     return {"response": context_msg, "status": "blocked_by_ga2"}

        # 3. LLM Generation (Dict 반환: response + analysis + state)
        llm_result = await llm_engine.ask(npc_id, message, history)
        raw_response = llm_result.get("response", "")

        # 4. Output Guardrail (페르소나 체크 등)
        is_output_safe, final_response = await ga_agent.validate_output(raw_response)
        
        # LLM 결과 검증 및 분석 데이터 추출
        analysis = llm_result.get("analysis", {})
        

        

        
        # 실제 DB 업데이트는 호출하는 쪽(router)이나 여기서 수행 가능
        # 현재 구조상 반환값에 포함시켜 router에서 처리하거나,
        # stats_service를 여기서 호출하여 즉시 반영할 수도 있음.
        # 기존 로직 유지를 위해 반환값에 반영
        
        return {
            "response": final_response,
            "npcId": npc_id,
            "status": "success" if is_output_safe else "sanitized",
            "analysis": analysis,
            "state": llm_result.get("state") # state는 현재 스냅샷이므로 유지하되, 다음 턴에 반영됨
        }

    async def _get_recent_history(self, user_id: str, npc_id: str, limit: int = 5):
        """DB에서 해당 유저와 NPC의 최근 대화 내역을 가져옵니다."""
        cursor = self.collection.find(
            {"conversation.participants.name": {"$in": [user_id, npc_id]}}
        ).sort("_id", -1).limit(limit)
        
        logs = await cursor.to_list(length=limit)
        history = []
        for log in reversed(logs):
            for msg in log.get("conversation", {}).get("messages", []):
                history.append({"speaker": msg["speaker"], "content": msg["content"]})
        return history

    async def save_chat_log(self, log_data: DayLog):
        """복잡한 게임 로그 데이터를 저장"""
        # Pydantic 모델을 dict로 변환 (datetime 처리 포함)
        doc = log_data.model_dump()

        # 정제 작업: 예를 들어 메시지 내용의 공백 제거
        for msg in doc["conversation"]["messages"]:
            msg["content"] = msg["content"].strip()

        # MongoDB 저장
        result = await self.collection.insert_one(doc)
        return str(result.inserted_id)

    # 기존 ChatService 내부에 추가
    async def save_story_summary(self, summary_data: StorySummary):
        """LLM이 생성한 스토리 요약 및 분석 결과를 저장"""
        # model_dump(by_alias=True)를 사용해야 'with' 필드가 제대로 저장됩니다.
        doc = summary_data.model_dump(by_alias=True)

        # 중복 저장 방지 (day_index 기준 upsert)
        result = await self.db["story_summaries"].update_one(
            {"day_index": doc["day_index"]},
            {"$set": doc},
            upsert=True
        )
        return "updated" if result.matched_count else "inserted"

    async def handle_troll_event(self, user_id: str, action_type: str, reason: str) -> bool:
        """
        트롤 이벤트를 기록하고, 레벨이 평계치(3)에 도달하면 True 반환 (Skip Trigger)
        """
        day_index = await self._get_current_day_index(user_id)
        
        user_state = await self.db["user_states"].find_one({"user_id": user_id})
        if not user_state:
            user_state = {"user_id": user_id, "troll_count": 0, "day_index": day_index}
        
        current_count = user_state.get("troll_count", 0) + 1
        
        await self.db["user_states"].update_one(
            {"user_id": user_id},
            {"$set": {"troll_count": current_count, "day_index": day_index}},
            upsert=True
        )
        
        print(f"🚨 [Troll] User {user_id} Warning ({current_count}/3) - {reason}")
        
        # 3. 임계치 체크
        if current_count >= 3:
            await self._skip_to_next_day(user_id, day_index)
            return True
            
        return False

    async def _get_current_day_index(self, user_id: str) -> int:
        """유저의 현재 진행 일차(Day Index)를 조회"""
        # 1. UserState 확인
        user_state = await self.db["user_states"].find_one({"user_id": user_id})
        if user_state and "day_index" in user_state:
            return user_state["day_index"]
            
        # 2. 없다면 StorySummary(회고록)에서 가장 최근 날짜 조회
        latest_summary = await self.db["story_summaries"].find_one(
            sort=[("day_index", -1)] # TODO: user_id 필드가 story_summaries에 있다면 필터 추가 필요
        )
        if latest_summary:
            return latest_summary["day_index"] + 1
            
        # 3. 기본값 1
        return 1

    async def _skip_to_next_day(self, user_id: str, day_index: int):
        """
        강제로 하루를 종료하고, '망쳐버린 하루' 요약을 생성하여 저장.
        """
        print(f"💀 [Troll] User {user_id} - Day {day_index} FORCED SKIP")
        
        # 1. 망친 하루 요약 저장
        failed_summary = StorySummary(
            day_index=day_index,
            diary=Diary(
                title="망쳐버린 하루",
                text="오늘 하루종일 이상한 소리만 하다가 시간을 낭비했다. 마을 사람들의 시선이 따갑다.",
                tone="regretful"
            ),
            summary_bullets=[
                "플레이어의 불손한 태도로 인해 대화가 단절됨",
                "마을에서 평판이 급격히 하락함",
                "아무런 소득 없이 하루를 마감함"
            ],
            key_conversations=[],
            items=[],
            clues=[],
            troll_level_analysis=TrollAnalysis(
                delta_total=3,
                top_causes=["abusive_language", "safety_violation"]
            ),
            consistency_check=ConsistencyCheck(
                contradictions_found=[],
                missing_info=[]
            ),
            ending=GameEnding(
                status="continue",
                ending_type="failure",
                reason="Troll limit exceeded",
                required_next_step="be_polite"
            ),
            flags_for_next_day=[
                NextDayFlag(flag="villager_hostility", why="Player Trolling")
            ],
            safety=SafetyCheck(
                hallucination_risk="low",
                spoiler_blocked=True
            )
        )
        
        await self.save_story_summary(failed_summary)
        
        # 2. 유저 상태 업데이트 (다음 날로, 트롤 카운트 리셋)
        await self.db["user_states"].update_one(
            {"user_id": user_id},
            {"$set": {
                "day_index": day_index + 1,
                "troll_count": 0
            }}
        )

chat_service = ChatService()