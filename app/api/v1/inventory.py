from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.inventory import InventoryResponse, ItemActionRequest, ExploreRequest, ExploreResponse
from app.services.inventory_service import inventory_service
from app.services.stats_service import stats_service
from app.core.security import get_current_user_id

router = APIRouter()

@router.get("", response_model=InventoryResponse, summary="인벤토리 조회")
async def get_inventory(user_id: str = Depends(get_current_user_id)):
    """유저가 보유한 아이템 목록과 녹음 파일 정보를 모두 가져옵니다."""
    return await inventory_service.get_user_inventory(user_id)

@router.post("/add", response_model=InventoryResponse, summary="아이템 추가")
async def add_item(data: ItemActionRequest, user_id: str = Depends(get_current_user_id)):
    """특정 아이템 코드를 인벤토리에서 보유(True) 상태로 변경합니다."""
    try:
        return await inventory_service.add_item(user_id, data.item_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"아이템 추가 중 오류: {str(e)}")

@router.post("/use", summary="아이템 사용")
async def use_item(data: ItemActionRequest, user_id: str = Depends(get_current_user_id)):
    """아이템을 사용 처리하여 미보유(False) 상태로 변경합니다. 아이템이 없으면 404를 반환합니다."""
    success = await inventory_service.use_item(user_id, data.item_id)
    
    if success is None:
        raise HTTPException(status_code=404, detail="해당 아이템을 보유하고 있지 않습니다.")
        
    return {
        "status": "success", 
        "message": f"{data.item_id} 아이템을 사용했습니다."
    }


@router.post("/explore", response_model=ExploreResponse, summary="탐색으로 아이템 획득")
async def explore_zone(data: ExploreRequest, user_id: str = Depends(get_current_user_id)):
    """
    floor_id / room_id / active_zone_id를 기준으로 map의 itemId를 확인하고
    아이템이 있으면 인벤토리에 추가한 뒤 아이템 상세를 반환합니다.
    """
    hp_result = await stats_service.spend_hp(user_id, 1, "탐색")
    if not hp_result["success"]:
        raise HTTPException(status_code=400, detail=hp_result["message"])

    result = await inventory_service.explore_zone(
        user_id=user_id,
        floor_id=data.floor_id,
        room_id=data.room_id,
        active_zone_id=data.active_zone_id,
    )
    if not result.get("success", False):
        raise HTTPException(status_code=404, detail=result.get("message", "탐색 처리 중 오류가 발생했습니다."))
    return result
