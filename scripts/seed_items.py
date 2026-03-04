import asyncio
import json
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

async def seed_items():
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.DATABASE_NAME]
    
    with open("app/data/items.json", "r", encoding="utf-8") as f:
        items_dict = json.load(f)
        
    items_list = list(items_dict.values())
    
    await db["items"].delete_many({})
    if items_list:
        await db["items"].insert_many(items_list)
        print(f"✅ Successfully seeded {len(items_list)} items into 'items' collection.")

if __name__ == "__main__":
    asyncio.run(seed_items())
