import uuid
import json
import os
from datetime import datetime

from app.services.base_service import BaseService
from app.core.security import create_access_token, verify_token, create_refresh_token


class StatsService(BaseService):
    characters = ["believer_a", "believer_b", "believer_c", "friend", "reporter", "leader"]

    def __init__(self):
        super().__init__()
        self.collection_token = self.db["tokens"]
        self.collection_npc = self.db["npc"]

    async def refresh_session_token(self, refresh_token: str):
        """리프레시 토큰을 검증하고 새로운 액세스 토큰을 발급합니다."""
        user_id = verify_token(refresh_token)
        if not user_id:
            return None

        user_data = await self.collection_token.find_one({"user_id": user_id})
        if not user_data:
            return None

        new_access_token = create_access_token(user_id)

        return {
            "access_token": new_access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }

    async def get_current_stats(self, user_id: str):
        stats = await self.collection_token.find_one({"user_id": user_id})
        return stats

    async def get_current_NPC_stats(self, user_id: str, npc_id: str):
        stats = await self.collection_npc.find_one({"user_id": user_id, "npcId": npc_id})

        return stats

    async def update_stats(self, updates: dict, user_id: str):
        filter_query = {"user_id": user_id}

        update_query = {"$set": updates}

        await self.collection_token.update_one(
            filter_query,
            update_query,
            upsert=True  # 데이터가 없으면 새로 생성
        )

        return await self.get_current_stats(user_id)

    async def update_NPC_stats(self, updates: dict, npc_id: str, user_id: str):
        filter_query = {"user_id": user_id, "npcId": npc_id}
        update_query = {"$set": updates}

        await self.collection_npc.update_one(filter_query, update_query, upsert=True)

        return await self.get_current_NPC_stats(user_id, npc_id)

    async def static_stats(self):
        ''' 유저 스탯 생성 '''
        user_id = str(uuid.uuid4())
        token = create_access_token(user_id)
        refresh_token = create_refresh_token(user_id)

        initial_stats = {
            "user_id": user_id,
            "fishLevel": 0,
            "hp": 100,
            "friendly": 50,
            "trust": 0,
            "created_at": datetime.now()
        }
        await self.collection_token.insert_one(initial_stats)

        ''' NPC stats 생성 '''
        await self.insert_initial_npc_stats(user_id)

        ''' 초기 인벤토리 생성 (001-099) '''
        initial_items = {f"{i:03d}": (i <= 3) for i in range(1, 100)}
        await self.db["inventories"].insert_one({
            "user_id": user_id,
            "items": initial_items,
            "created_at": datetime.now()
        })

        return {
            "fishLevel": 0, "hp": 100, "friendly": 50, "token": token, "refresh_token": refresh_token, "trust": 0
        }
        
    async def insert_initial_npc_stats(self, user_id: str):
        file_path = os.path.join(os.path.dirname(__file__), "..", "data", "characters.json")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                npc_data_map = json.load(f)
                npc_documents = []
                for npc_name, stats in npc_data_map.items():
                    npc_documents.append({
                        "user_id": user_id,
                        "npcId": npc_name,  # believer_a, friend 등
                        "friendly": stats.get("friendly", 0),
                        "faith": stats.get("faith", 0),
                        "created_at": datetime.now()
                    })
                if npc_documents:
                    await self.collection_npc.insert_many(npc_documents)
        except FileNotFoundError:
            raise FileNotFoundError(f"Character data file not found at: {file_path}")


stats_service = StatsService()
