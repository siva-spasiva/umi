import asyncio
import os
import json
from app.core.database import db

async def sync_fish_levels():
    file_path = os.path.join(os.path.dirname(__file__), "..", "app", "data", "characters.json")
    with open(file_path, "r", encoding="utf-8") as f:
        npc_data_map = json.load(f)
        
    print(f"Loaded {len(npc_data_map)} characters from JSON.")
    updated_count = 0
    
    for npc_name, char_info in npc_data_map.items():
        if char_info.get("isHardcoded"):
            continue
            
        npc_stats = char_info.get("initialStats", {})
        fish_level = npc_stats.get("fishLevel", 0)
        
        # update all existing records for this NPC
        print(f"Updating {npc_name} -> fishLevel: {fish_level}")
        result = await db["npc_stats"].update_many(
            {"npcId": npc_name},
            {"$set": {"fishLevel": fish_level}}
        )
        updated_count += result.modified_count
        print(f"  - Modified {result.modified_count} users' records.")
        
    print(f"\nDone. Successfully synced {updated_count} total records.")

if __name__ == "__main__":
    asyncio.run(sync_fish_levels())
