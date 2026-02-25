from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from app.schemas.map import Floor, Room
from app.services.map_service import map_service
from app.services.conversation_service import conversation_service
from app.services.stats_service import stats_service
from app.services.inventory_service import inventory_service
from app.core.security import get_current_user_id
from app.core.database import db

router = APIRouter()

def _apply_dynamic_locks(maps_data, inventory_items):
    """
    유저가 소유한 아이템 목록을 기준으로 맵의 잠긴 구역(locked) 상태를 동적으로 해제합니다.
    (내부 데이터를 직접 수정하므로 반환값 없이 in-place로 동작합니다)
    """
    if not inventory_items:
        return

    # maps_data가 단일 맵(Dict)인지 리스트(List)인지 확인
    if isinstance(maps_data, dict):
        maps_list = [maps_data]
    else:
        maps_list = maps_data

    for floor in maps_list:
        for room in floor.get("rooms", []):
            for zone in room.get("activeZones", []):
                # 구역이 잠겨있고(locked가 dict 형태) 열쇠 조건(targetId)이 있는 경우
                if isinstance(zone.get("locked"), dict) and zone["locked"].get("targetId"):
                    target_id = zone["locked"]["targetId"]
                    if target_id in inventory_items:
                        # 아이템을 보유하고 있으면 잠금 해제 처리 (여기서 locked를 해제 상태로 변경)
                        # 또는 프론트가 인식할 수 있게 locked = False 등 적절한 플래그로 변경
                        # 주의: schema에서 Optional[dict] 이므로 필요시 bool 대신 dict나 None으로 해야될수도 있으나
                        # 기존 프론트와 협의된 lock_flag 스펙에 맞게 세팅.
                        # 프론트가 locked 유무 자체로 판단한다면 None으로 지워주거나, 명시적으로 false 형태의 dict를 사용할 수 있음
                        # 여기서는 사용자가 'lock_flag'를 응답하길 원했으므로 zone 자체에 lock_flag 속성을 추가
                        zone["lock_flag"] = False
                    else:
                        zone["lock_flag"] = True
                else:
                    # 기본적으로 잠긴 상태가 아니면 False
                    zone["lock_flag"] = False


@router.get("/", response_model=List[Floor])
async def get_all_maps(user_id: str = Depends(get_current_user_id)):
    """전체 맵 리스트를 반환합니다. 인벤토리 상황에 따라 잠김(locked) 상태가 동적으로 해제됩니다."""
    maps = await map_service.get_all_maps()
    
    # 유저 인벤토리 조회
    user_inventory = await inventory_service.get_user_inventory(user_id)
    # 보유 중(True)인 아이템 ID 목록만 추출 (예: ["item001", "item002"])
    owned_items = [item.get("id") for item in user_inventory.get("items", []) if item.get("owned")]
    
    # 보유한 아이템에 따라 잠금 다이나믹 해제
    _apply_dynamic_locks(maps, owned_items)
    
    return maps

@router.get("/{floor_id}", response_model=Floor)
async def get_floor(floor_id: str, user_id: str = Depends(get_current_user_id)):
    """특정 층의 맵 데이터를 반환합니다. 인벤토리 상황에 따라 잠김(locked) 상태가 동적으로 해제됩니다."""
    floor = await map_service.get_floor(floor_id)
    if not floor:
        raise HTTPException(status_code=404, detail=f"Floor {floor_id} not found")
        
    user_inventory = await inventory_service.get_user_inventory(user_id)
    owned_items = [item.get("id") for item in user_inventory.get("items", []) if item.get("owned")]
    
    _apply_dynamic_locks(floor, owned_items)
        
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
    NPC 배치 및 토픽 정보를 포함하여 반환합니다.
    (엿듣기 기능은 분리되었습니다. 인벤토리 상황에 따라 문 잠김 상태 동적 해제)
    """
    room = await map_service.get_room(floor_id, room_id)
    if not room:
        raise HTTPException(status_code=404, detail=f"Room {room_id} in {floor_id} not found")
        
    user_inventory = await inventory_service.get_user_inventory(user_id)
    owned_items = [item.get("id") for item in user_inventory.get("items", []) if item.get("owned")]
    _apply_dynamic_locks({"rooms": [room]}, owned_items)
    
    response = {"room": room, "npcs": [], "topic": None, "single_npc": None}
    
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
                
                if room_placement.get("topic"):
                    response["topic"] = room_placement["topic"]
                if room_placement.get("npcs"):
                    response["npcs"] = room_placement["npcs"]
                
                # NPC가 1명만 있을 때 누가 있는지 인지하는 기능 추가
                if len(npcs) == 1:
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


@router.post("/{floor_id}/room/{room_id}/eavesdrop")
async def eavesdrop_room(
    floor_id: str,
    room_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    특정 방에서 NPC들의 대화를 엿듣습니다 (최초 엿듣기).
    HP 5를 소모하며 자동 생성된 대화를 반환합니다.
    """
    room = await map_service.get_room(floor_id, room_id)
    if not room:
        raise HTTPException(status_code=404, detail=f"Room {room_id} in {floor_id} not found")
        
    user_doc = await db["users"].find_one({"user_id": user_id})
    if not user_doc or "progress" not in user_doc:
        raise HTTPException(status_code=400, detail="유저 진행 상태를 찾을 수 없습니다.")

    day_index = user_doc["progress"].get("current_day", 1)
    session_index = user_doc["progress"].get("current_session", 1)
    
    session_state = await db["session_map_state"].find_one(
        {"day_index": day_index, "session_index": session_index},
        {"_id": 0}
    )
    
    if not session_state:
        raise HTTPException(status_code=404, detail="해당 세션의 맵 정보가 없습니다.")
        
    room_placement = None
    for placement in session_state.get("room_placements", []):
        if placement.get("room_id") == room_id:
            room_placement = placement
            break
            
    if not room_placement or len(room_placement.get("npcs", [])) < 2 or not room_placement.get("topic"):
        raise HTTPException(status_code=400, detail="이 방에서 엿들을 수 있는 대화가 없습니다.")
        
    npcs = room_placement.get("npcs", [])
    
    # HP 소모 (5) — NPC 대화 엿듣기
    hp_result = await stats_service.spend_hp(user_id, 5, "방 엿듣기")
    if not hp_result["success"]:
        raise HTTPException(status_code=400, detail=hp_result["message"])

    topic_data = room_placement["topic"]
    topic_text = f"{topic_data.get('title', '')}: {topic_data.get('context', '')}"
    npc_ids_lower = [npc.lower() for npc in npcs]
    
    try:
        conversation = await conversation_service.start_auto_conversation(
            topic=topic_text,
            npc_ids=npc_ids_lower,
            num_turns=6
        )
        
        return {
            "npcs": npcs,
            "topic": topic_data,
            "conversation": conversation.model_dump(),
            "can_eavesdrop_more": True
        }
    except Exception as e:
        print(f"[WARN] Eavesdrop generation failed: {e}")
        raise HTTPException(status_code=500, detail="대화 생성 중 오류가 발생했습니다.")

