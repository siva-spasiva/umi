from pydantic import BaseModel, Field
from typing import Dict, Optional, Any, List

class NPCStat(BaseModel):
    friendly: int = Field(50, description="NPC와의 친밀도 (0-100)")
    faith: int = Field(50, description="NPC의 신앙심 또는 충성도 (0-100)")
    fishLevel: int = Field(0, description="NPC와 관련된 물고기 레벨")

class FirstStatsResponse(BaseModel):
    fishLevel: int = Field(..., description="초기 물고기 레벨")
    hp: int = Field(..., description="초기 체력")

class StatsResponse(BaseModel):
    fishLevel: int = Field(..., description="현재 물고기 레벨")
    hp: int = Field(..., description="현재 체력")

class StatsUpdate(BaseModel):
    updates: Dict[str, Any] = Field(..., description="업데이트할 스탯 필드와 값의 딕셔너리", example={"hp": 80, "fishLevel": 3})

class NPCStatsUpdate(BaseModel):
    npcId: str = Field(..., description="대상 NPC의 고유 ID")
    updates: Dict[str, int] = Field(..., description="업데이트할 NPC 스탯 필드와 값", example={"friendly": 60})

class SuccessResponse(BaseModel):
    status: str = Field("success", description="요청 처리 결과 상태")


# ── HP 관리 관련 스키마 ──

class SpendHpRequest(BaseModel):
    cost: int = Field(..., ge=1, description="소모할 HP 양")
    room_id: Optional[str] = Field(None, description="현재 방 ID (휴식 가능 여부 판별용)")

class PenaltyInfo(BaseModel):
    amount: int = Field(..., description="페널티 HP")
    message: str = Field("피곤하다...", description="페널티 메시지")

class SectionTransitionInfo(BaseModel):
    message: str = Field(..., description="전환 메시지")
    target_room: Optional[str] = Field(None, description="이동할 방")
    next_period: str = Field(..., description="다음 시간대")
    next_day: Optional[int] = Field(None, description="다음 날짜 (하루 넘어갈 때만)")
    hp_after: int = Field(..., description="전환 후 HP")
    plus_hp_after: int = Field(0, description="전환 후 plusHp")
    penalty: Optional[PenaltyInfo] = Field(None, description="페널티 정보")

class SpendHpResponse(BaseModel):
    success: bool = Field(..., description="HP 소모 성공 여부")
    hp: int = Field(..., description="소모 후 base HP")
    plus_hp: int = Field(..., description="소모 후 plusHp")
    current_period: str = Field(..., description="현재 시간대")
    current_day: int = Field(..., description="현재 날짜")
    transition: Optional[SectionTransitionInfo] = Field(None, description="섹션 전환 발생 시 정보")

class HpCostPreviewRequest(BaseModel):
    cost: int = Field(..., ge=1, description="확인할 HP 소모량")

class HpCostPreviewResponse(BaseModel):
    affordable: bool = Field(..., description="소모 가능 여부")
    will_transition: bool = Field(False, description="섹션 전환 발생 여부")
    from_period: Optional[str] = Field(None, description="현재 시간대")
    to_period: Optional[str] = Field(None, description="전환 후 시간대")
    new_hp: Optional[int] = Field(None, description="소모 후 예상 HP")
