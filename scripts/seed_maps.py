import asyncio
import json
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

async def seed_maps():
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.DATABASE_NAME]
    
    with open("app/data/map.json", "r", encoding="utf-8") as f:
        map_data = json.load(f)
        
    await db["maps"].delete_many({})
    if map_data:
        await db["maps"].insert_many(map_data)
        print(f"✅ Successfully seeded {len(map_data)} floors into 'maps' collection.")

if __name__ == "__main__":
    asyncio.run(seed_maps())
