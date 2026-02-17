from typing import Optional, Dict, Any
from app.services.base_service import BaseService

class InventoryService(BaseService):
    def __init__(self):
        super().__init__()

    async def get_user_inventory(self, user_id: str) -> Dict[str, Any]:
        inventory = await self.db["inventories"].find_one({"user_id": user_id})
        records = await self.db["records"].find_one({"user_id": user_id})
        if not inventory:
            return {"user_id": user_id, "items": {}, "record_files" : []}
        
        if records and "record_files" in records:
            inventory["record_files"] = records["record_files"]
        else:
            inventory["record_files"] = []
        return inventory

    async def add_item(self, user_id: str, item_id: str):
        """아이템을 획득 상태(True)로 변경합니다."""
        await self.db["inventories"].update_one(
            {"user_id": user_id},
            {"$set": {f"items.{item_id}": True}}
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
