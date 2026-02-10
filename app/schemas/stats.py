from pydantic import BaseModel, Field
from typing import Dict, Optional, Any

class NPCStat(BaseModel):
    friendly: int = Field(50, description="NPC와의 친밀도 (0-100)")
    faith: int = Field(50, description="NPC의 신앙심 또는 충성도 (0-100)")
    fishLevel: int = Field(0, description="NPC와 관련된 물고기 레벨")

class FirstStatsResponse(BaseModel):
    fishLevel: int = Field(..., description="초기 물고기 레벨")
    hp: int = Field(..., description="초기 체력")
    friendly: int = Field(..., description="초기 유저 친밀도")
    trust : int = Field(..., description="초기 신뢰도")
    token : str = Field(..., description="발급된 Access Token")
    refresh_token: str = Field(..., description="발급된 Refresh Token")

class StatsResponse(BaseModel):
    fishLevel: int = Field(..., description="현재 물고기 레벨")
    hp: int = Field(..., description="현재 체력")
    friendly: int = Field(..., description="현재 유저 친밀도")
    faith: int = Field(..., description="현재 신앙심")
    trust: int = Field(..., description="현재 신뢰도")

class StatsUpdate(BaseModel):
    updates: Dict[str, Any] = Field(..., description="업데이트할 스탯 필드와 값의 딕셔너리", example={"hp": 80, "trust": 10})

class NPCStatsUpdate(BaseModel):
    npcId: str = Field(..., description="대상 NPC의 고유 ID (예: believer_a)")
    updates: Dict[str, int] = Field(..., description="업데이트할 NPC 스탯 필드와 값", example={"friendly": 60})

class SuccessResponse(BaseModel):
    status: str = Field("success", description="요청 처리 결과 상태")
