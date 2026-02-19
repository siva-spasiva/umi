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


from typing import List, Union

@router.post(
    "/conversation/start",
    response_model=List[ConversationResponse],
    summary="NPC 자동 대화 시작 (스케줄 or 수동)",
    description=(
        "NPC들이 자동으로 대화합니다.\n"
        "- **수동 모드**: npc_ids, topic 지정 (단일 대화)\n"
        "- **스케줄 모드**: day_index, session 지정 (스케줄 기반 다중 대화)\n"
        "반환값은 항상 대화 목록(List)입니다."
    )
)
async def start_conversation(
    request: ConversationStartRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    NPC 자동 대화 시작
    
    [입력 파라미터]
    1. 스케줄 모드:
        - day_index: 1~7
        - session: morning, afternoon, evening
    2. 수동 모드:
        - topic: 주제
        - npc_ids: NPC ID 목록
    """
    try:
        # 스케줄 모드
        if request.day_index is not None and request.session is not None:
            results = await conversation_service.trigger_scheduled_conversations(
                day_index=request.day_index,
                session=request.session
            )
            return results
        
        # 수동 모드 (기존 로직)
        if not request.topic or not request.npc_ids:
            raise HTTPException(status_code=400, detail="수동 모드에서는 topic과 npc_ids가 필수입니다.")
            
        result = await conversation_service.start_auto_conversation(
            topic=request.topic,
            npc_ids=request.npc_ids,
            num_turns=request.num_turns,
        )
        return [result]
        
    except HTTPException:
        raise
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
