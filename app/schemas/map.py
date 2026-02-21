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

class Room(BaseModel):
    id: str
    name: str
    namePrefix: Optional[str] = None
    highlightText: Optional[str] = None
    highlightColor: Optional[str] = None
    description: str
    background: Optional[str] = None
    overlayColor: Optional[str] = None
    npcId: Optional[str] = None
    activeZones: List[ActiveZone] = Field(default_factory=list)

class Floor(BaseModel):
    floor_id: str
    name: str
    description: str
    mapImage: Optional[str] = None
    rooms: List[Room] = Field(default_factory=list)

class MapConfigResponse(BaseModel):
    data: List[Floor]
