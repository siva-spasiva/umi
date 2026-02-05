from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
import uuid
from datetime import datetime

class RecordService:
    def __init__(self):
        self.client = AsyncIOMotorClient(settings.MONGODB_URL)
        self.db = self.client[settings.DATABASE_NAME]
        self.collection = self.db["records"]

    async def save_recording(self, user_id: str, messages: list, title: str = None):
        """대화 리스트를 별도의 records 컬렉션에 저장합니다."""
        record_id = str(uuid.uuid4())
        new_record = {
            "record_id": record_id,
            "user_id": user_id,
            "title": title or f"대화 기록 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "messages": messages,
            "created_at": datetime.now()
        }
        await self.collection.insert_one(new_record)
        return record_id

    async def get_recording(self, user_id: str, record_id: str):
        """특정 녹음 파일을 조회합니다."""
        return await self.collection.find_one({"user_id": user_id, "record_id": record_id})

    async def get_user_recordings(self, user_id: str):
        """유저의 모든 녹음 목록을 가져옵니다 (내용 제외 가능)."""
        cursor = self.collection.find(
            {"user_id": user_id},
            {"messages": 0} # 목록 조회 시 대화 내용은 제외하여 성능 최적화
        ).sort("created_at", -1)
        
        return await cursor.to_list(length=100)

record_service = RecordService()