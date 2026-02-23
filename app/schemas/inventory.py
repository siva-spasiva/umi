from pydantic import BaseModel, Field
from typing import Dict, Optional, List, Any


class ItemDetail(BaseModel):
    """인벤토리 내 아이템 상세 정보"""
    id: str = Field(..., description="아이템 고유 코드 (예: 'item001')")
    name: str = Field("", description="아이템 이름")
    description: str = Field("", description="아이템 설명")
    flavorText: str = Field("", description="아이템 플레이버 텍스트")
    type: str = Field("normal", description="아이템 타입 (normal, key_item)")
    owned: bool = Field(False, description="보유 여부")
    consumable: Optional[bool] = Field(None, description="소모 가능 여부")
    effect: Optional[Dict[str, Any]] = Field(None, description="사용 효과")
    npcOrigin: Optional[str] = Field(None, description="NPC 출처")
    isContract: Optional[bool] = Field(None, description="계약서 여부")
    roomItem: Optional[bool] = Field(None, description="방 아이템 여부")


class InventoryResponse(BaseModel):
    user_id: str = Field(..., description="유저 고유 ID")
    items: List[ItemDetail] = Field(default_factory=list, description="아이템 목록 (전체 상세 정보 포함)")
    record_files: Optional[List[Dict]] = Field([], description="유저와 관련된 녹음 파일 메타데이터 목록")


class ItemActionRequest(BaseModel):
    item_id: str = Field(..., description="아이템 고유 코드 (예: 'item001')", example="item001")


class ExploreRequest(BaseModel):
    floor_id: str = Field(..., description="탐색할 층 ID (예: '1F')")
    room_id: str = Field(..., description="탐색할 방 ID (예: 'main_hall')")
    active_zone_id: str = Field(..., description="탐색할 액티브존 ID")


class ExploreResponse(BaseModel):
    success: bool = Field(..., description="탐색 처리 성공 여부")
    floor_id: str = Field(..., description="층 ID")
    room_id: str = Field(..., description="방 ID")
    active_zone_id: str = Field(..., description="액티브존 ID")
    item_found: bool = Field(..., description="아이템 존재 여부")
    item: Optional[ItemDetail] = Field(None, description="획득한 아이템 상세")
    message: str = Field(..., description="탐색 결과 메시지")
