from app.services.base_service import BaseService
from app.schemas.chat import DayLog
from app.schemas.story import StorySummary
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
        # 1. GA1: 입력 안전성 검증
        is_safe, safety_msg = await ga1_agent.check_safety(message)
        if not is_safe:
            return {"response": safety_msg, "status": "blocked_by_ga1"}

        # 2. GA2: 문맥 및 세계관 검증
        # TODO : 아직 GA2모델이 개발되지 않아서 사용 (History는 LLM에 전달)
        history = await self._get_recent_history(user_id, npc_id, limit=5)
        # is_context_ok, context_msg = await ga2_context.check_context(message, history)
        # if not is_context_ok:
        #     return {"response": context_msg, "status": "blocked_by_ga2"}

        # 3. LLM Generation
        raw_response = await llm_engine.ask(npc_id, message, history)

        # 4. Output Guardrail (페르소나 체크 등)
        is_output_safe, final_response = await ga_agent.validate_output(raw_response)
        
        return {
            "response": final_response,
            "npcId": npc_id,
            "status": "success" if is_output_safe else "sanitized"
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

chat_service = ChatService()