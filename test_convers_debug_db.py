import asyncio
from app.core.database import db

async def refill_hp():
    await db["user_stats"].update_one(
        {"user_id": "test_user_001"},
        {"$set": {"total_hp": 9999, "session_hp": 9999, "plus_hp": 0}}
    )
    print("Refilled HP")

asyncio.run(refill_hp())
