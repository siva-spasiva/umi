from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime

class Diary(BaseModel):
    title: str
    text: str
    tone: str

class KeyConversation(BaseModel):
    speaker_with: str = Field(alias="with") # 'with'는 파이썬 예약어라 별칭 사용
    what_changed: str
    quote: Optional[str] = None

class ItemUsage(BaseModel):
    name: str
    how_used_or_implication: str

class Clue(BaseModel):
    info: str
    importance: Literal["low", "mid", "high"]

class TrollAnalysis(BaseModel):
    delta_total: int
    top_causes: List[str]

class ConsistencyCheck(BaseModel):
    contradictions_found: List[str]
    missing_info: List[str]

class GameEnding(BaseModel):
    status: Literal["continue", "ending_triggered"]
    ending_type: Literal["escape", "assimilation", "exposed", "sacrifice", "failure", "twist", "null"]
    reason: str
    required_next_step: str

class NextDayFlag(BaseModel):
    flag: str
    why: str

class SafetyCheck(BaseModel):
    hallucination_risk: Literal["low", "mid", "high"]
    spoiler_blocked: bool

class StorySummary(BaseModel):
    day_index: int
    diary: Diary
    summary_bullets: List[str]
    key_conversations: List[KeyConversation]
    items: List[ItemUsage]
    clues: List[Clue]
    troll_level_analysis: TrollAnalysis
    consistency_check: ConsistencyCheck
    ending: GameEnding
    flags_for_next_day: List[NextDayFlag]
    safety: SafetyCheck
    time: datetime = Field(default_factory=datetime.now)