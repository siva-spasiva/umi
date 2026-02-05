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
            description="새로운 유저 ID를 생성하고, 기본 스탯 및 NPC 스탯, 초기 인벤토리(001-003 보유)를 설정한 뒤 인증 토큰을 발급합니다."
            )
async def static_stats():
    return await stats_service.static_stats()

@router.post("/refresh", response_model=TokenResponse,
             summary="토큰 재발급",
             description="만료된 Access Token을 대신하여 유효한 Refresh Token으로 새로운 Access Token을 발급받습니다.",
             responses={
                 401: {"description": "유효하지 않거나 만료된 리프레시 토큰"}
             })
async def refresh_token(data: RefreshTokenRequest):
    res = await stats_service.refresh_session_token(data.refresh_token)
    if not res:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 리프레시 토큰입니다.")
    return res
