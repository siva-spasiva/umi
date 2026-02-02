import re
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.schemas.chat import DayLog
from app.schemas.story import StorySummary

class ChatService:
    def __init__(self):
        self.client = AsyncIOMotorClient(settings.MONGODB_URL)
        self.db = self.client[settings.DATABASE_NAME]
        self.collection = self.db["chat_logs"]

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