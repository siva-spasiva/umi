from typing import Optional, Dict, Any, List
from datetime import datetime
from app.services.base_service import BaseService

class InventoryService(BaseService):
    def __init__(self):
        super().__init__()

    async def _build_item_list(self, owned_map: Dict[str, bool]) -> List[Dict[str, Any]]:
        """items 컬렉션에서 전체 아이템 정보를 가져와 보유 여부를 합산합니다."""
        all_items = await self.db["items"].find({}, {"_id": 0}).to_list(length=200)
        
        result = []
        for item in all_items:
            item_id = item.get("id", "")
            item["owned"] = owned_map.get(item_id, False)
            result.append(item)
        
        return result

    async def get_user_inventory(self, user_id: str) -> Dict[str, Any]:
        inventory = await self.db["inventories"].find_one({"user_id": user_id})
        
        # 신규 유저인 경우 (인벤토리 데이터가 없음): 시작 아이템 3종(001, 002, 003) 지급
        if not inventory:
            starting_items = {"item001": True, "item002": True, "item003": True}
            await self.db["inventories"].insert_one({
                "user_id": user_id,
                "items": starting_items
            })
            owned_map = starting_items
        else:
            owned_map = inventory.get("items", {})
            
        records = await self.db["records"].find_one({"user_id": user_id})
        items_list = await self._build_item_list(owned_map)
        
        record_files = []
        if records and "record_files" in records:
            record_files = records["record_files"]
        
        return {
            "user_id": user_id,
            "items": items_list,
            "record_files": record_files
        }

    async def add_item(self, user_id: str, item_id: str):
        """아이템을 획득 상태(True)로 변경하고, 이벤트를 기록합니다."""
        await self.db["inventories"].update_one(
            {"user_id": user_id},
            {
                "$set": {f"items.{item_id}": True},
                "$setOnInsert": {"user_id": user_id}
            },
            upsert=True
        )
        
        # 아이템 이벤트 기록
        item_info = await self.db["items"].find_one({"id": item_id}, {"_id": 0})
        item_name = item_info.get("name", item_id) if item_info else item_id
        await self.db["item_events"].insert_one({
            "user_id": user_id,
            "item_id": item_id,
            "item_name": item_name,
            "action": "acquired",
            "description": item_info.get("description", "") if item_info else "",
            "timestamp": datetime.utcnow()
        })
        print(f"📦 [Item] 아이템 획득 이벤트 기록: {item_name} ({item_id})")
        
        return await self.get_user_inventory(user_id)

    async def use_item(self, user_id: str, item_id: str):
        """아이템을 사용 완료 상태(False)로 변경하고, 이벤트를 기록합니다."""
        inventory = await self.db["inventories"].find_one(
            {"user_id": user_id}
        )
        
        if not inventory or not inventory.get("items", {}).get(item_id):
            return None # 아이템 없음
            
        await self.db["inventories"].update_one(
            {"user_id": user_id},
            {"$set": {f"items.{item_id}": False}}
        )
        
        # 아이템 이벤트 기록
        item_info = await self.db["items"].find_one({"id": item_id}, {"_id": 0})
        item_name = item_info.get("name", item_id) if item_info else item_id
        await self.db["item_events"].insert_one({
            "user_id": user_id,
            "item_id": item_id,
            "item_name": item_name,
            "action": "used",
            "description": item_info.get("description", "") if item_info else "",
            "timestamp": datetime.utcnow()
        })
        print(f"🔧 [Item] 아이템 사용 이벤트 기록: {item_name} ({item_id})")
        
        return True

    async def get_item_info(self, item_id: str) -> Optional[Dict[str, Any]]:
        """아이템 상세 정보를 DB에서 조회합니다."""
        return await self.db["items"].find_one({"_id": item_id})

    async def check_item_ownership(self, user_id: str, item_id: str) -> bool:
        """유저가 해당 아이템을 보유(True)하고 있는지 확인합니다."""
        inventory = await self.db["inventories"].find_one({"user_id": user_id})
        if not inventory:
            return False
            
        # 보유하고 있고(True), 사용완료(False)되지 않은 상태여야 함
        return inventory.get("items", {}).get(item_id, False) is True

    async def _get_floor_doc(self, floor_id: str) -> Optional[Dict[str, Any]]:
        """맵 컬렉션에서 층 문서를 조회합니다. (floor_id/id 모두 지원)"""
        return await self.db["maps"].find_one(
            {"$or": [{"floor_id": floor_id}, {"id": floor_id}]},
            {"_id": 0}
        )

    async def explore_zone(self, user_id: str, floor_id: str, room_id: str, active_zone_id: str) -> Dict[str, Any]:
        """
        특정 activeZone을 탐색하여 itemId가 있으면 아이템을 획득 처리합니다.
        - itemId가 없으면 item_found=False 반환
        - itemId가 있으면 add_item과 동일하게 인벤토리에 추가 + 이벤트 기록
        """
        floor_doc = await self._get_floor_doc(floor_id)
        if not floor_doc:
            return {
                "success": False,
                "floor_id": floor_id,
                "room_id": room_id,
                "active_zone_id": active_zone_id,
                "item_found": False,
                "item": None,
                "message": f"층을 찾을 수 없습니다: {floor_id}",
            }

        room_doc = None
        for room in floor_doc.get("rooms", []):
            if room.get("id") == room_id:
                room_doc = room
                break

        if not room_doc:
            return {
                "success": False,
                "floor_id": floor_id,
                "room_id": room_id,
                "active_zone_id": active_zone_id,
                "item_found": False,
                "item": None,
                "message": f"방을 찾을 수 없습니다: {room_id}",
            }

        zone_doc = None
        for zone in room_doc.get("activeZones", []):
            if zone.get("id") == active_zone_id:
                zone_doc = zone
                break

        if not zone_doc:
            return {
                "success": False,
                "floor_id": floor_id,
                "room_id": room_id,
                "active_zone_id": active_zone_id,
                "item_found": False,
                "item": None,
                "message": f"액티브존을 찾을 수 없습니다: {active_zone_id}",
            }

        item_id = (zone_doc.get("itemId") or "").strip()
        if not item_id:
            return {
                "success": True,
                "floor_id": floor_id,
                "room_id": room_id,
                "active_zone_id": active_zone_id,
                "item_found": False,
                "item": None,
                "message": "해당 구역에는 획득 가능한 아이템이 없습니다.",
            }

        item_info = await self.db["items"].find_one({"id": item_id}, {"_id": 0})
        if not item_info:
            return {
                "success": False,
                "floor_id": floor_id,
                "room_id": room_id,
                "active_zone_id": active_zone_id,
                "item_found": False,
                "item": None,
                "message": f"아이템 정보를 찾을 수 없습니다: {item_id}",
            }

        await self.add_item(user_id, item_id)
        item_info["owned"] = True

        return {
            "success": True,
            "floor_id": floor_id,
            "room_id": room_id,
            "active_zone_id": active_zone_id,
            "item_found": True,
            "item": item_info,
            "message": f"{item_info.get('name', item_id)} 아이템을 획득했습니다.",
        }

inventory_service = InventoryService()
