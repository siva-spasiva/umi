from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.stats import StatsResponse, StatsUpdate, FirstStatsResponse, SuccessResponse, NPCStatsUpdate, NPCStat
from app.schemas.auth import TokenResponse, RefreshTokenRequest
from app.services.stats_service import stats_service
from app.core.security import get_current_user_id

router = APIRouter()

@router.get("/stats", response_model=StatsResponse,
            summary="현재 유저 스탯 조회",
            description="현재 로그인한 유저의 HP, 물고기 레벨, 신뢰도 등 전반적인 스탯 정보를 가져옵니다."
            )
async def get_stats(user_id: str = Depends(get_current_user_id)):
    return await stats_service.get_current_stats(user_id)

@router.post("/stats", response_model=FirstStatsResponse,
             summary="유저 스탯 업데이트",
             description="유저의 특정 스탯 값을 수정합니다. 전달된 필드만 부분적으로 업데이트됩니다."
             )
async def update_stats(data: StatsUpdate, user_id: str = Depends(get_current_user_id)):
    return await stats_service.update_stats(data.updates, user_id)

@router.post("/stats/NPC", response_model=NPCStat,
             summary="NPC 스탯 업데이트",
             description="특정 NPC의 친밀도나 신앙심 스탯을 수정합니다."
             )
async def update_NPC_stats(data: NPCStatsUpdate, user_id: str = Depends(get_current_user_id)):
    return await stats_service.update_NPC_stats(data.updates, data.npcId, user_id)

@router.get("/stats/static", response_model=FirstStatsResponse,
            summary="초기 게임 세션 생성",
            description="인증된 유저 ID로 초기 스탯 및 NPC 스탯, 초기 인벤토리를 설정합니다. (토큰 발급 X)"
            )
async def static_stats(user_id: str = Depends(get_current_user_id)):
    return await stats_service.static_stats(user_id)

# refresh_token endpoint removed (moved to user.py)
