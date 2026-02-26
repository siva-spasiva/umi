from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from app.agents.llm_engine import llm_engine
from app.core.database import db
from app.core.security import get_current_user_id

router = APIRouter()

class SetStateRequest(BaseModel):
    npc_id: str
    friendly: int = Field(..., ge=0, le=100)
    faith: int = Field(..., ge=0, le=100)

class SetSessionHpRequest(BaseModel):
    session_hp: int = Field(..., ge=0, description="설정할 세션 HP")
    plus_hp: int | None = Field(default=None, ge=0, description="선택값: 이월 HP")
    total_hp: int | None = Field(default=None, ge=0, description="선택값: 총 HP")


@router.post("/debug/set_npc_state")
async def set_npc_state(request: SetStateRequest):
    """
    [DEBUG] NPC 상태 강제 설정
    테스트 목적으로 특정 NPC의 친밀도/신뢰도를 변경합니다.
    """
    try:
        llm_engine.set_npc_state(request.npc_id, request.friendly, request.faith)
        return {"status": "success", "npc_id": request.npc_id, "friendly": request.friendly, "faith": request.faith}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/reset_troll_count")
async def reset_troll_count(user_id: str = Depends(get_current_user_id)):
    """
    [DEBUG] 유저의 troll_count 초기화
    - user_id/body 입력 없이 Authorization 토큰으로 유저를 식별합니다.
    - day_index도 입력받지 않고, 현재 저장된 유저 상태를 기준으로 자동 결정합니다.
    """
    try:
        user_state = await db["user_states"].find_one({"user_id": user_id})
        if user_state and "day_index" in user_state:
            current_day_index = user_state["day_index"]
        else:
            # user_states가 없으면 user_stats의 current_day를 fallback으로 사용
            user_stats = await db["user_stats"].find_one({"user_id": user_id})
            current_day_index = user_stats.get("current_day", 0) if user_stats else 0

        await db["user_states"].update_one(
            {"user_id": user_id},
            {"$set": {"troll_count": 0, "day_index": current_day_index}},
            upsert=True
        )

        updated = await db["user_states"].find_one(
            {"user_id": user_id},
            {"_id": 0, "user_id": 1, "day_index": 1, "troll_count": 1}
        )

        return {"status": "success", "data": updated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/set_session_hp")
async def set_session_hp(
    request: SetSessionHpRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    [DEBUG] 현재 유저의 session_hp를 강제 설정
    - Swagger 임시 테스트용
    - Authorization 토큰으로 유저 식별
    """
    try:
        existing = await db["user_stats"].find_one({"user_id": user_id})
        if not existing:
            raise HTTPException(status_code=404, detail="user_stats가 없습니다. /stats/static을 먼저 호출하세요.")

        update_fields = {"session_hp": request.session_hp}
        if request.plus_hp is not None:
            update_fields["plus_hp"] = request.plus_hp
        if request.total_hp is not None:
            update_fields["total_hp"] = request.total_hp

        await db["user_stats"].update_one(
            {"user_id": user_id},
            {"$set": update_fields}
        )

        updated = await db["user_stats"].find_one(
            {"user_id": user_id},
            {"_id": 0, "user_id": 1, "total_hp": 1, "session_hp": 1, "plus_hp": 1, "current_session": 1, "current_day": 1}
        )

        return {"status": "success", "data": updated}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/debug/reset_items")
async def reset_items(user_id: str = Depends(get_current_user_id)):
    """
    [DEBUG] 유저 인벤토리 초기화
    - 모든 아이템 소유 상태를 해제하고 시초 아이템(001, 002, 003)만 소지하도록 만듭니다.
    - Authorization 토큰으로 유저 식별
    """
    try:
        inventory = await db["inventories"].find_one({"user_id": user_id})
        if not inventory:
            raise HTTPException(status_code=404, detail="인벤토리를 찾을 수 없습니다. /stats/static 등을 먼저 호출하세요.")

        # Dictionary comprehension: set item001~003 to True, others to False
        reset_items_map = {f"item{str(i).zfill(3)}": (i <= 3) for i in range(1, 100)}
        
        await db["inventories"].update_one(
            {"user_id": user_id},
            {"$set": {"items": reset_items_map}}
        )

        return {"status": "success", "message": "아이템이 성공적으로 초기화되었습니다."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
