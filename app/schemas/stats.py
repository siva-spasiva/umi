from pydantic import BaseModel, Field
from typing import Dict, Optional, Any, List

class NPCStat(BaseModel):
    friendly: int = Field(50, description="NPC와의 친밀도 (0-100)")
    faith: int = Field(50, description="NPC의 신앙심 또는 충성도 (0-100)")
    fishLevel: int = Field(0, description="NPC와 관련된 물고기 레벨")

class FirstStatsResponse(BaseModel):
    fishLevel: int = Field(..., description="초기 물고기 레벨")
    total_hp: int = Field(100, description="하루 총 HP")
    session_hp: int = Field(30, description="초기 세션 HP")
    plus_hp: int = Field(0, description="이월 HP")
    current_session: str = Field("morning", description="현재 세션")
    current_session_index: int = Field(1, description="현재 세션 인덱스 (1=morning, 2=afternoon, 3=evening, 4=night)")
    current_day: int = Field(0, description="현재 날짜 (0=튜토리얼)")

class StatsResponse(BaseModel):
    fishLevel: int = Field(..., description="현재 물고기 레벨")
    total_hp: int = Field(..., description="하루 남은 총 HP")
    session_hp: int = Field(..., description="현재 세션 남은 HP")
    plus_hp: int = Field(..., description="이월 HP")
    current_session: str = Field(..., description="현재 세션 (morning/afternoon/evening/night)")
    current_session_index: int = Field(..., description="현재 세션 인덱스 (1~4)")
    current_day: int = Field(..., description="현재 날짜 (0=튜토리얼, 1~5=본게임)")

class StatsUpdate(BaseModel):
    updates: Dict[str, Any] = Field(..., description="업데이트할 스탯 필드와 값의 딕셔너리", example={"hp": 80, "fishLevel": 3})

class NPCStatsUpdate(BaseModel):
    npcId: str = Field(..., description="대상 NPC의 고유 ID")
    updates: Dict[str, int] = Field(..., description="업데이트할 NPC 스탯 필드와 값", example={"friendly": 60})

class SuccessResponse(BaseModel):
    status: str = Field("success", description="요청 처리 결과 상태")


# ── HP 관리 관련 스키마 ──

class SpendHpRequest(BaseModel):
    hp: int = Field(..., ge=1, description="소모할 HP 양")
    message: Optional[str] = Field(None, description="HP 소모 사유")

class SpendHpResponse(BaseModel):
    success: bool = Field(..., description="HP 소모 성공 여부")
    total_hp: int = Field(..., description="하루 남은 총 HP")
    session_hp: int = Field(..., description="현재 세션 남은 HP (음수 = 다음 세션에서 차감)")
    plus_hp: int = Field(..., description="이월 HP")
    current_session: str = Field(..., description="현재 세션")
    current_session_index: int = Field(..., description="현재 세션 인덱스 (1~4)")
    current_day: int = Field(..., description="현재 날짜")
    session_depleted: bool = Field(False, description="세션 HP 소진 여부 (True면 더 이상 행동 불가)")
    message: Optional[str] = Field(None, description="결과 메시지")

class AdvanceSessionResponse(BaseModel):
    success: bool = Field(..., description="세션 전환 성공 여부")
    previous_session: str = Field(..., description="이전 세션")
    previous_session_index: int = Field(..., description="이전 세션 인덱스")
    current_session: str = Field(..., description="전환 후 세션")
    current_session_index: int = Field(..., description="전환 후 세션 인덱스")
    total_hp: int = Field(..., description="하루 남은 총 HP")
    session_hp: int = Field(..., description="새 세션 HP")
    plus_hp: int = Field(..., description="이월된 HP")
    current_day: int = Field(..., description="현재 날짜")
    message: Optional[str] = Field(None, description="전환 메시지")
