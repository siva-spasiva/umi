from fastapi import APIRouter, HTTPException
from typing import List, Optional
from app.schemas.map import Floor, Room
from app.services.map_service import map_service

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

@router.get("/{floor_id}/room/{room_id}", response_model=Room)
async def get_room(floor_id: str, room_id: str):
    """특정 층의 특정 방 데이터를 반환합니다."""
    room = await map_service.get_room(floor_id, room_id)
    if not room:
        raise HTTPException(status_code=404, detail=f"Room {room_id} in {floor_id} not found")
    return room
