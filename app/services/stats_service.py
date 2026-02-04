import uuid
import json
import os
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.core.security import create_access_token


class StatsService:
    characters = ["believer_a", "believer_b", "believer_c", "friend", "reporter", "leader"]

    def __init__(self):
        self.client = AsyncIOMotorClient(settings.MONGODB_URL)
        self.db = self.client[settings.DATABASE_NAME]
        self.collection_token = self.db["tokens"]
        self.collection_npc = self.db["npc"]

    async def get_current_stats(self, user_id: str):
        # 실제로는 유저 ID별로 가져와야 함 (우선 단일 데이터 가정)
        stats = await self.db["stats"].find_one({"user_id": user_id})
        return stats

    async def get_current_NPC_stats(self, user_id: str, npc_id: str):
        stats = await self.db["npc"].find_one({"userId": user_id, "npcId": npc_id})

        # if stats:
            # stats["_id"] = str(stats["_id"])  # JSON 변환을 위해 ObjectId를 문자열로!

        return stats

    async def update_stats(self, updates: dict, user_id: str):
        filter_query = {"userId": user_id}

        update_query = {"$set": updates}

        await self.db["npc"].update_one(
            filter_query,
            update_query,
            upsert=True  # 데이터가 없으면 새로 생성
        )

        return await self.get_current_stats(user_id)

    async def update_NPC_stats(self, updates: dict, npc_id: str, user_id: str):
        filter_query = {"userId": user_id, "npcId": npc_id}
        update_query = {"$set": updates}

        await self.db["npc"].update_one(filter_query, update_query, upsert=True)

        return await self.get_current_NPC_stats(user_id, npc_id)

    async def static_stats(self):
        # user_stats = await self.collection_token.find_one({"userId": user_id})
        user_id = str(uuid.uuid4())
        token = create_access_token(user_id)

        initial_stats = {
            "userId": user_id,
            "fishLevel": 0,
            "hp": 100,
            "friendly": 50,
            "trust": 0,
            "created_at": datetime.now()
        }
        await self.collection_token.insert_one(initial_stats)

        ''' NPC stats 생성 '''
        await self.insert_initial_npc_stats(user_id)

        return {
            "fishLevel": 0, "hp": 100, "friendly": 50, "token": token, "trust": 0
        }

    # return {
    #     "fishLevel": user_stats["fishLevel"],
    #     "hp": user_stats["hp"],
    #     "friendly": user_stats['friendly'],
    #     "trust": user_stats['trust'],
    #     "token": token
    # }

    async def insert_initial_npc_stats(self, user_id: str):
        file_path = os.path.join(os.path.dirname(__file__), "..", "data", "characters.json")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                npc_data_map = json.load(f)
                npc_documents = []
                for npc_name, stats in npc_data_map.items():
                    npc_documents.append({
                        "userId": user_id,  # 소유자 식별
                        "npcId": npc_name,  # believer_a, friend 등
                        "friendly": stats.get("friendly", 0),
                        "faith": stats.get("faith", 0),
                        "created_at": datetime.now()
                    })
                if npc_documents:
                    # 여러 문서를 한 번에 저장
                    await self.collection_npc.insert_many(npc_documents)
        except FileNotFoundError:
            raise "Not find characters data"


stats_service = StatsService()
