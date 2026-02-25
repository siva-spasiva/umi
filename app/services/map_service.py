from app.services.base_service import BaseService
from typing import List, Dict, Optional

class MapService(BaseService):
    def __init__(self):
        super().__init__()
        self.collection = self.db["maps"]

    async def get_all_maps(self) -> List[dict]:
        """전체 맵 리스트를 반환합니다."""
        cursor = self.collection.find({}, {"_id": 0})
        maps = await cursor.to_list(length=100)
        return maps

    async def get_floor(self, floor_id: str) -> Optional[dict]:
        """특정 층의 맵 데이터를 반환합니다."""
        document = await self.collection.find_one({"id": floor_id}, {"_id": 0})
        return document

    async def get_room(self, floor_id: str, room_id: str) -> Optional[dict]:
        """특정 층의 방 하나를 찾아서 반환합니다."""
        document = await self.collection.find_one({"id": floor_id}, {"_id": 0})
        if not document:
            return None
        
        rooms = document.get("rooms", [])
        for room in rooms:
            if room.get("id") == room_id:
                return room
        
        return None

map_service = MapService()
