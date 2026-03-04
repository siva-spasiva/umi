import asyncio
from app.core.database import db

async def run():
    cursor = db["inventories"].find({})
    async for doc in cursor:
        items = doc.get("items", {})
        new_items = {}
        changed = False
        for k, v in items.items():
            if k.isdigit() and len(k) == 3:
                new_items[f"item{k}"] = v
                changed = True
            else:
                new_items[k] = v
        if changed:
            await db["inventories"].update_one(
                {"_id": doc["_id"]},
                {"$set": {"items": new_items}}
            )
            print(f"Updated inventory for {doc['user_id']}")
    print("Done")

asyncio.run(run())
