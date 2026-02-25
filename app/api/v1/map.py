from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from app.schemas.map import Floor, Room
from app.services.map_service import map_service
from app.services.conversation_service import conversation_service
from app.services.stats_service import stats_service
from app.core.security import get_current_user_id
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
    user_id: str = Depends(get_current_user_id)
):
    """
    특정 층의 특정 방 데이터를 반환합니다.
    유저 정보를 통해 현재 day와 session에 맞는
    NPC 배치 및 토픽 정보를 기반으로 엿듣기(eavesdrop) 혹은 single_npc 데이터를 반환합니다.
    """
    room = await map_service.get_room(floor_id, room_id)
    if not room:
        raise HTTPException(status_code=404, detail=f"Room {room_id} in {floor_id} not found")
    
    response = {"room": room, "eavesdrop": None}
    
    # DB에서 현재 사용자의 진행 상태(일자 및 세션) 조회
    user_doc = await db["users"].find_one({"user_id": user_id})
    if not user_doc or "progress" not in user_doc:
        return response

    day_index = user_doc["progress"].get("current_day", 1)
    session_index = user_doc["progress"].get("current_session", 1)
    
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
            
            if room_placement:
                npcs = room_placement.get("npcs", [])
                
                # NPC가 2명 이상이고 대화 주제가 있을 때 (기존 엿듣기 기능)
                if len(npcs) >= 2 and room_placement.get("topic"):
                    # HP 소모 (5) — NPC 대화 미리보기
                    hp_result = await stats_service.spend_hp(user_id, 5, "방 엿듣기")
                    if not hp_result["success"]:
                        response["eavesdrop"] = None
                        response["hp_error"] = hp_result["message"]
                        return response

                    topic_data = room_placement["topic"]
                    topic_text = f"{topic_data.get('title', '')}: {topic_data.get('context', '')}"
                    npc_ids_lower = [npc.lower() for npc in npcs]
                    
                    try:
                        conversation = await conversation_service.start_auto_conversation(
                            topic=topic_text,
                            npc_ids=npc_ids_lower,
                            num_turns=6
                        )
                        
                        response["eavesdrop"] = {
                            "npcs": npcs,
                            "topic": topic_data,
                            "conversation": conversation.model_dump(),
                            "can_eavesdrop_more": True
                        }
                    except Exception as e:
                        print(f"[WARN] Eavesdrop generation failed: {e}")
                        response["eavesdrop"] = None
                
                # NPC가 1명만 있을 때 누가 있는지 인지하는 기능 추가
                elif len(npcs) == 1:
                    npc_id = npcs[0]
                    
                    # characters.json에서 해당 NPC의 한국어 이름 조회
                    try:
                        import json
                        import os
                        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
                        chars_path = os.path.join(base_dir, "app", "data", "characters.json")
                        with open(chars_path, "r", encoding="utf-8") as f:
                            chars_data = json.load(f)
                            # 소문자로 비교하여 찾거나 기본 id 사용
                            npc_name = chars_data.get(npc_id.lower(), {}).get("name", npc_id)
                    except Exception as e:
                        print(f"[WARN] Failed to load NPC name for {npc_id}: {e}")
                        npc_name = npc_id

                    response["single_npc"] = {
                        "npc_id": npc_id,
                        "npc_name": npc_name,
                        "message": f"방 안에 {npc_name}의 기척이 느껴진다..."
                    }
    
    return response

