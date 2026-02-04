import jwt
from datetime import datetime, timedelta, timezone
from app.core.config import settings
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SECRET_KEY = settings.JWT_SECRET_KEY  # .env에서 관리 권장
ALGORITHM = settings.JWT_ALGORITHM

security_scheme = HTTPBearer()


def create_access_token(new_id: str):
    print(f"[DEBUG] 생성 시 키: {SECRET_KEY}")  # 터미널 확인용
    payload = {
        "sub": str(new_id),
        "exp": datetime.now(timezone.utc) + timedelta(days=3000)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str):
    print(f"[DEBUG] 검증 시 키: {SECRET_KEY}")  # 터미널 확인용
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except Exception as e:
        print(f"[DEBUG] 검증 실패 원인: {e}")
        return None


def get_current_user_id(res: HTTPAuthorizationCredentials = Depends(security_scheme)):
    token = res.credentials
    print(f"token : {token}")
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    return user_id
