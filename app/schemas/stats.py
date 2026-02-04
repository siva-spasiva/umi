from pydantic import BaseModel
from typing import Dict, Optional, Any

class NPCStat(BaseModel):
    friendly: int = 50
    faith: int = 50
    fishLevel: int = 0

class FirstStatsResponse(BaseModel):
    fishLevel: int
    hp: int
    friendly: int
    trust : int
    token : str

class StatsResponse(BaseModel):
    fishLevel: int
    hp: int
    friendly: int
    faith: int
    trust: int

class StatsUpdate(BaseModel):
    updates: Dict[str, Any]

class NPCStatsUpdate(BaseModel):
    npcId: str
    updates: Dict[str, int]

class SuccessResponse(BaseModel):
    status: str = "success"
