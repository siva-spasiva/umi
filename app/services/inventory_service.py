from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional, Dict, Any
from app.core.config import settings

class InventoryService:
    def __init__(self):
        self.client = AsyncIOMotorClient(settings.MONGODB_URL)
        self.db = self.client[settings.DATABASE_NAME]

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

inventory_service = InventoryService()
