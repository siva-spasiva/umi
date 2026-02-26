import asyncio
from app.agents.llm_engine import llm_engine
from app.agents.npc_pipeline import NPCPromptLoader

async def run():
    print("Sending message to bingo...")
    result = await llm_engine.ask("gwakbing", "너 여기서 뭐하는 거야? 도대체 무슨 속셈이지? 전부 다 말해봐.")
    print("\n--- RESPONSE ---")
    print(result["response"])

asyncio.run(run())
