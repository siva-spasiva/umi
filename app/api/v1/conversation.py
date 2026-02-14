"""
NPC 대화(Conversation) API 라우터
- POST /conversation/start  — NPC-only 자동 대화
- POST /conversation/reply  — User+NPC 대화 (유저 메시지 전달)
"""

from fastapi import APIRouter, HTTPException, status, Depends
from app.schemas.conversation import (
    ConversationStartRequest,
    ConversationReplyRequest,
    ConversationResponse,
)
from app.services.conversation_service import conversation_service
from app.core.security import get_current_user_id

router = APIRouter()


@router.post(
    "/conversation/start",
    response_model=ConversationResponse,
    summary="NPC 자동 대화 시작",
    description=(
        "지정한 NPC들이 주제를 정해 자동으로 대화합니다 (유저 참여 X). "
        "NPC 1~3명이 num_turns만큼 번갈아가며 대화를 생성합니다."
    )
)
async def start_conversation(
    request: ConversationStartRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    NPC-only 자동 대화

    - topic: 대화 주제
    - npc_ids: 참여 NPC ID 목록 (1~3명)
    - num_turns: 자동 대화 턴 수 (기본 5)
    """
    try:
        result = await conversation_service.start_auto_conversation(
            topic=request.topic,
            npc_ids=request.npc_ids,
            num_turns=request.num_turns,
        )
        return result
    except Exception as e:
        print(f"[ERROR] conversation/start: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"NPC 자동 대화 생성 중 오류: {str(e)}"
        )


@router.post(
    "/conversation/reply",
    response_model=ConversationResponse,
    summary="User+NPC 대화 (유저 메시지 전달)",
    description=(
        "유저가 메시지를 보내면, 참여 NPC들이 순서대로 응답합니다. "
        "이전 대화 내역(history)을 함께 전달하면 맥락을 유지합니다."
    )
)
async def reply_conversation(
    request: ConversationReplyRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    User+NPC 대화

    - topic: 대화 주제
    - npc_ids: 참여 NPC ID 목록 (1~3명)
    - user_message: 유저의 발언
    - history: 이전 대화 턴들 (Optional)
    """
    try:
        result = await conversation_service.process_user_reply(
            topic=request.topic,
            npc_ids=request.npc_ids,
            user_message=request.user_message,
            history=request.history,
        )
        return result
    except Exception as e:
        print(f"[ERROR] conversation/reply: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"NPC 대화 응답 생성 중 오류: {str(e)}"
        )
