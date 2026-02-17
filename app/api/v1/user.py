from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from app.services.user_service import user_service
from app.schemas.auth import TokenResponse, RefreshTokenRequest

router = APIRouter()

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    refresh_token: str

@router.post("/users/login", response_model=LoginResponse,
             summary="익명 로그인 (토큰 발급)",
             description="새로운 유저 ID를 생성하고 Access/Refresh Token을 발급합니다."
             )
async def login():
    return await user_service.login_anonymous()

@router.post("/users/refresh", response_model=TokenResponse,
             summary="토큰 재발급",
             description="유효한 Refresh Token으로 새로운 Access Token을 발급받습니다.",
             responses={
                 401: {"description": "유효하지 않거나 만료된 리프레시 토큰"}
             })
async def refresh_token(data: RefreshTokenRequest):
    res = await user_service.refresh_session_token(data.refresh_token)
    if not res:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 리프레시 토큰입니다.")
    return res
