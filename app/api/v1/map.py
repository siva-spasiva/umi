from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from app.schemas.map import Floor, Room
from app.services.map_service import map_service
from app.services.conversation_service import conversation_service
from app.core.database import db

router = APIRouter()

@router.get("/", response_model=List[Floor])
async def get_all_maps():
    """전체 맵 리스트를 반환합니다."""
    maps = await map_service.get_all_maps()
    return maps

@router.get("/{floor_id}", response_model=Floor)
async def get_floor(floor_id: str):
    """특정 층의 맵 데이터를 반환합니다."""
    floor = await map_service.get_floor(floor_id)
    if not floor:
        raise HTTPException(status_code=404, detail=f"Floor {floor_id} not found")
    return floor

@router.get("/{floor_id}/room/{room_id}")
async def get_room(
    floor_id: str,
    room_id: str,
    day_index: Optional[int] = Query(None, description="현재 게임 일차 (1~5)"),
    session_index: Optional[int] = Query(None, description="현재 세션 인덱스 (1~4)")
):
    """
    특정 층의 특정 방 데이터를 반환합니다.
    day_index와 session_index를 함께 전달하면, end-session에서 미리 저장해 둔
    NPC 배치 및 토픽 정보를 기반으로 엿듣기(eavesdrop) 대화 6턴을 생성합니다.
    """
    room = await map_service.get_room(floor_id, room_id)
    if not room:
        raise HTTPException(status_code=404, detail=f"Room {room_id} in {floor_id} not found")
    
    response = {"room": room, "eavesdrop": None}
    
    if day_index is not None and session_index is not None:
        session_state = await db["session_map_state"].find_one(
            {"day_index": day_index, "session_index": session_index},
            {"_id": 0}
        )
        
        if session_state:
            room_placement = None
            for placement in session_state.get("room_placements", []):
                if placement.get("room_id") == room_id:
                    room_placement = placement
                    break
            
            if room_placement and len(room_placement.get("npcs", [])) >= 2 and room_placement.get("topic"):
                topic_data = room_placement["topic"]
                topic_text = f"{topic_data.get('title', '')}: {topic_data.get('context', '')}"
                npc_ids_lower = [npc.lower() for npc in room_placement["npcs"]]
                
                try:
                    conversation = await conversation_service.start_auto_conversation(
                        topic=topic_text,
                        npc_ids=npc_ids_lower,
                        num_turns=6
                    )
                    
                    response["eavesdrop"] = {
                        "npcs": room_placement["npcs"],
                        "topic": topic_data,
                        "conversation": conversation.model_dump(),
                        "can_eavesdrop_more": True
                    }
                except Exception as e:
                    print(f"[WARN] Eavesdrop generation failed: {e}")
                    response["eavesdrop"] = None
    
    return response


class EavesdropRequest(BaseModel):
    """추가 엿듣기 요청 — 방 정보만 넘기면 서버가 알아서 처리"""
    day_index: int = Field(..., description="현재 게임 일차")
    session_index: int = Field(..., description="현재 세션 인덱스")
    room_id: str = Field(..., description="엿듣기 중인 방 ID")


@router.post("/eavesdrop", summary="추가 엿듣기")
async def eavesdrop_more(request: EavesdropRequest):
    """
    NPC 대화를 추가로 엿듣습니다.
    day_index, session_index, room_id만 전달하면 서버가 session_map_state에서
    해당 방의 NPC와 토픽을 읽어 새로운 6턴 대화를 생성합니다.
    """
    session_state = await db["session_map_state"].find_one(
        {"day_index": request.day_index, "session_index": request.session_index},
        {"_id": 0}
    )
    
    if not session_state:
        raise HTTPException(status_code=404, detail="해당 세션의 맵 정보가 없습니다.")
    
    room_placement = None
    for placement in session_state.get("room_placements", []):
        if placement.get("room_id") == request.room_id:
            room_placement = placement
            break
    
    if not room_placement or len(room_placement.get("npcs", [])) < 2 or not room_placement.get("topic"):
        raise HTTPException(status_code=404, detail="이 방에서 엿들을 수 있는 대화가 없습니다.")
    
    topic_data = room_placement["topic"]
    topic_text = f"{topic_data.get('title', '')}: {topic_data.get('context', '')}"
    npc_ids_lower = [npc.lower() for npc in room_placement["npcs"]]
    
    try:
        conversation = await conversation_service.start_auto_conversation(
            topic=topic_text,
            npc_ids=npc_ids_lower,
            num_turns=6
        )
        return {
            "conversation": conversation.model_dump(),
            "can_eavesdrop_more": True
        }
    except Exception as e:
        print(f"[ERROR] eavesdrop: {e}")
        raise HTTPException(status_code=500, detail=f"엿듣기 생성 중 오류: {str(e)}")
