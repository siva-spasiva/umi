from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Optional, Any, List


class Participant(BaseModel):
    name: str
    time: datetime = Field(default_factory=datetime.now)

class Message(BaseModel):
    speaker: str
    content: str
    time: datetime = Field(default_factory=datetime.now)

class Conversation(BaseModel):
    participants: List[Participant]
    messages : List[Message]

class ItemAcquired(BaseModel):
    item_name: str
    time: datetime = Field(default_factory=datetime.now)

class InformationAcquired(BaseModel):
    item_name: str
    time: datetime = Field(default_factory=datetime.now)

class InfoAcquired(BaseModel):
    info: str
    time: datetime = Field(default_factory=datetime.now)

class TrollEvent(BaseModel):
    action: str
    troll_level_change: int
    time: datetime = Field(default_factory=datetime.now)

class StateSnapshot(BaseModel):
    fish_level: int
    sanity: int
    trust_friendA: int
    troll_level: int
    location: str
    time_of_day: str

# 2. 메인 스키마 (최종 저장 형태)
class DayLog(BaseModel):
    day_index: int
    conversation: Conversation
    items_acquired: List[ItemAcquired] = []
    information_acquired: List[InfoAcquired] = []
    troll_level_events: List[TrollEvent] = []
    state_snapshot: StateSnapshot

class ChatRequest(BaseModel):
    message: str
    npcId: str
    userId: Optional[str] = "user_dev_session"

class ChatResponse(BaseModel):
    response: str
    thought: str
    npcId: str
    updatedStats: Dict[str, Any]
    currentStats: Dict[str, Any]