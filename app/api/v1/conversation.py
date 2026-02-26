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
from app.services.stats_service import stats_service
from app.services.schedule_service import schedule_service
from app.core.database import db

router = APIRouter()


from typing import List

@router.post(
    "/conversation/start",
    response_model=List[ConversationResponse],
    summary="NPC 자동 대화 시작 (room_id 기반 엿듣기)",
    description=(
        "NPC들이 자동으로 대화합니다.\n"
        "- room_id를 지정하면 토큰 기반 현재 day/session을 조회해\n"
        "  해당 방의 NPC 배치/토픽으로 엿듣기 대화를 생성합니다.\n"
        "반환값은 항상 대화 목록(List)입니다."
    )
)
async def start_conversation(
    request: ConversationStartRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    NPC 자동 대화 시작
    """
    try:
        if not request.room_id:
            raise HTTPException(status_code=400, detail="room_id는 필수입니다.")

        current_stats = await stats_service.get_current_stats(user_id)
        day_index = int(current_stats.get("current_day", 0))
        session_index = int(current_stats.get("current_session_index", 1))
        target_room_id = request.room_id.strip().lower()

        session_state = await db["session_map_state"].find_one(
            {"day_index": day_index, "session_index": session_index},
            {"_id": 0}
        )
        if not session_state:
            session_state = await schedule_service.generate_map_config(day_index, session_index)
            await db["session_map_state"].update_one(
                {"day_index": day_index, "session_index": session_index},
                {"$set": session_state},
                upsert=True
            )

        room_placement = None
        for placement in session_state.get("room_placements", []):
            placement_room_id = str(placement.get("room_id", "")).strip().lower()
            if placement_room_id == target_room_id:
                room_placement = placement
                break

        if not room_placement:
            raise HTTPException(status_code=404, detail=f"현재 세션에서 room_id={target_room_id} 배치를 찾을 수 없습니다.")

        npcs = room_placement.get("npcs", [])
        topic_data = room_placement.get("topic")
        if len(npcs) < 2:
            raise HTTPException(status_code=400, detail="해당 방은 현재 엿듣기 가능한 NPC 조합(2인 이상)이 아닙니다.")
        if not topic_data:
            raise HTTPException(status_code=400, detail="해당 방의 대화 주제가 아직 생성되지 않았습니다.")

        topic_text = f"{topic_data.get('title', '')}: {topic_data.get('context', '')}"
        result = await conversation_service.start_auto_conversation(
            topic=topic_text,
            npc_ids=npcs,
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
            user_id=user_id,
        )
        return result
    except Exception as e:
        print(f"[ERROR] conversation/reply: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"NPC 대화 응답 생성 중 오류: {str(e)}"
        )
