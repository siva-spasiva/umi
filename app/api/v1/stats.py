from fastapi import APIRouter, Depends
from app.schemas.stats import StatsResponse, StatsUpdate, FirstStatsResponse, SuccessResponse, NPCStatsUpdate, NPCStat
from app.services.stats_service import stats_service
from app.core.security import get_current_user_id

router = APIRouter()

@router.get("/stats", response_model=StatsResponse,
            summary="대화 요약 정보 가져오기",
            description="대화 요약 정보 가져오기는 API"
            )
async def get_stats(user_id: str = Depends(get_current_user_id)):
    return await stats_service.get_current_stats(user_id)

@router.post("/stats", response_model=FirstStatsResponse,
             summary="스탯 수정하는 API",
             description="스탯 수정하는 API "
             )
async def update_stats(data: StatsUpdate, user_id: str = Depends(get_current_user_id)):
    return await stats_service.update_stats(data.updates, user_id)

@router.post("/stats/NPC", response_model=NPCStat,
             summary="NPC 스탯 수정하는 API",
             description="NPC 스탯 수정하는 API "
             )
async def update_NPC_stats(data: NPCStatsUpdate, user_id: str = Depends(get_current_user_id)):
    return await stats_service.update_NPC_stats(data.updates, data.npcId, user_id)

@router.get("/stats/static", response_model=FirstStatsResponse,
            summary="처음 기본 스탯 세팅",
            description="처음 기본 스택 세팅하는 API, 기본 유저 스텟과 NPC 스텟 생성"
            )
async def static_stats():
    return await stats_service.static_stats()
