from pydantic import BaseModel, Field
from typing import Dict, Optional, Any, List


class ConversationStartRequest(BaseModel):
    """NPC-only 자동 대화 요청"""
    topic: Optional[str] = Field(None, description="대화 주제 (스케줄 모드 시 자동 생성 가능)")
    npc_ids: Optional[List[str]] = Field(None, description="참여 NPC ID 목록 (수동 모드 시 필수)")
    num_turns: int = Field(default=5, description="자동 대화 턴 수", ge=1, le=20)
    day_index: Optional[int] = Field(None, description="스케줄 기반 대화 시 필요 (1~7)")
    session: Optional[str] = Field(None, description="스케줄 기반 대화 시 필요 (morning/afternoon/evening)")


class ConversationReplyRequest(BaseModel):
    """User+NPC 대화 요청 (유저 메시지 전달 후 NPC들 응답)"""
    topic: str = Field(..., description="대화 주제")
    npc_ids: List[str] = Field(..., description="참여 NPC ID 목록 (1~3명)", min_length=1, max_length=3)
    user_message: str = Field(..., description="유저의 발언")
    history: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="이전 대화 턴들 (speaker, speaker_id, content)"
    )


class ConversationTurn(BaseModel):
    """대화 한 턴"""
    speaker: str = Field(..., description="발언자 이름 (NPC 한국어 이름 or 'user')")
    speaker_id: str = Field(..., description="발언자 ID (NPC ID or 'user')")
    content: str = Field(..., description="대사 내용")
    analysis: Optional[Dict[str, Any]] = Field(
        default=None,
        description="의도 분석 결과 (reason_tags, friendly_delta, faith_delta)"
    )


class ConversationResponse(BaseModel):
    """NPC 대화 응답"""
    topic: str
    turns: List[ConversationTurn]
    npc_states: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="NPC별 현재 상태 {npc_id: {friendly, faith, ...}}"
    )
