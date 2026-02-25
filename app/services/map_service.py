from app.services.base_service import BaseService
from typing import List, Dict, Optional

class MapService(BaseService):
    def __init__(self):
        super().__init__()
        self.collection = self.db["maps"]

    def _normalize_room_npc(self, room: Dict) -> None:
        """
        room dict에서 npcId / npcIds를 정규화한다.
        - npcId가 문자열이면 콤마 기준으로 쪼개 npcIds 리스트로 변환
        - npcId 키는 응답에서 제거
        """
        raw_npc = room.get("npcId")

        npc_ids: List[str] = []

        if isinstance(raw_npc, list):
            npc_ids = [str(x).strip() for x in raw_npc if str(x).strip()]
        elif isinstance(raw_npc, str):
            npc_ids = [p.strip() for p in raw_npc.split(",") if p.strip()]

        # 기존 npcIds가 있다면 그대로 두고, 없을 때만 세팅
        if npc_ids and not room.get("npcIds"):
            room["npcIds"] = npc_ids

        # 더 이상 단일 필드는 사용하지 않으므로 제거
        if "npcId" in room:
            room.pop("npcId", None)

    async def get_all_maps(self) -> List[dict]:
        """전체 맵 리스트를 반환합니다."""
        cursor = self.collection.find({}, {"_id": 0})
        maps = await cursor.to_list(length=100)

        # NPC 정보 정규화: 항상 리스트 형태의 npcIds만 제공
        for floor in maps:
            rooms = floor.get("rooms", [])
            for room in rooms:
                self._normalize_room_npc(room)

        return maps

    async def get_floor(self, floor_id: str) -> Optional[dict]:
        """특정 층의 맵 데이터를 반환합니다."""
        document = await self.collection.find_one({"id": floor_id}, {"_id": 0})
        if not document:
            return None

        # 층 단위 조회 시에도 포맷 정규화
        for room in document.get("rooms", []):
            self._normalize_room_npc(room)

        return document

    async def get_room(self, floor_id: str, room_id: str) -> Optional[dict]:
        """특정 층의 방 하나를 찾아서 반환합니다."""
        document = await self.collection.find_one({"id": floor_id}, {"_id": 0})
        if not document:
            return None
        
        rooms = document.get("rooms", [])
        for room in rooms:
            if room.get("id") == room_id:
                self._normalize_room_npc(room)
                return room
        
        return None

map_service = MapService()
