from typing import Optional, Dict, Any, List
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
        """아이템을 획득 상태(True)로 변경합니다."""
        await self.db["inventories"].update_one(
            {"user_id": user_id},
            {
                "$set": {f"items.{item_id}": True},
                "$setOnInsert": {"user_id": user_id}
            },
            upsert=True
        )
        return await self.get_user_inventory(user_id)

    async def use_item(self, user_id: str, item_id: str):
        """아이템을 사용 완료 상태(False)로 변경합니다."""
        inventory = await self.db["inventories"].find_one(
            {"user_id": user_id}
        )
        
        if not inventory or not inventory.get("items", {}).get(item_id):
            return None # 아이템 없음
            
        await self.db["inventories"].update_one(
            {"user_id": user_id},
            {"$set": {f"items.{item_id}": False}}
        )
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

inventory_service = InventoryService()
