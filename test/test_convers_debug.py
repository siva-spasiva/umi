import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
import asyncio
from app.agents.npc_pipeline import NPCPromptLoader
from app.agents.npc_dialogue_engine import NPCState

loader = NPCPromptLoader("app/data/NPC_prompt.json", "app/data/characters.json")
core = loader.get_core_prompt("bingeo", 50)
print("=== CORE PROMPT (bingeo) ===")
print(core)
print("\n=== DYNAMIC RULES ===")
dyn = loader.retrieve_dynamic_rules("bingeo", 50, "안녕? 넌 누구야?", 5)
print(dyn)
