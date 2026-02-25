import asyncio
import httpx
from app.core.security import create_access_token

async def run():
    token = create_access_token("test_user")
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "topic": "test",
        "npc_ids": ["NPC_KWAK_01", "NPC_CHEONG_02"],
        "num_turns": 2
    }
    
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post("http://localhost:8000/api/v1/conversation/start", json=payload, headers=headers, timeout=60)
            print("STATUS:", r.status_code)
            print("RESPONSE:", r.text)
        except Exception as e:
            print(e)

asyncio.run(run())
