from pydantic import BaseModel, Field
from typing import Dict, Optional, List

class InventoryResponse(BaseModel):
    user_id: str = Field(..., description="유저 고유 ID")
    items: Dict[str, bool] = Field(..., description="아이템 코드(001-099)별 보유 여부 (True: 보유)")
    record_files: Optional[List[Dict]] = Field([], description="유저와 관련된 녹음 파일 메타데이터 목록")

class ItemActionRequest(BaseModel):
    item_id: str = Field(..., description="아이템 고유 코드 (예: '001')", example="001")
    
