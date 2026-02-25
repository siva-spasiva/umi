from pydantic import BaseModel, Field
from typing import List, Optional

class ActiveZone(BaseModel):
    id: str
    type: str = Field(..., description="move, info, item, inspect, rest 등")
    target: Optional[str] = None
    x: float
    y: float
    width: float
    height: float
    label: str
    message: str
    itemId: Optional[str] = None
    locked: Optional[dict] = None
    lock_flag: Optional[bool] = None

class Room(BaseModel):
    id: str
    name: str
    namePrefix: Optional[str] = None
    highlightText: Optional[str] = None
    highlightColor: Optional[str] = None
    description: str
    background: Optional[str] = None
    overlayColor: Optional[str] = None
    # 한 방에 여러 NPC가 있을 수 있으므로 리스트로만 관리
    npcIds: List[str] = Field(default_factory=list)
    activeZones: List[ActiveZone] = Field(default_factory=list)

class Floor(BaseModel):
    id: str
    name: str
    description: str
    mapImage: Optional[str] = None
    rooms: List[Room] = Field(default_factory=list)

class MapConfigResponse(BaseModel):
    data: List[Floor]
