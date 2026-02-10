import jwt
from datetime import datetime, timedelta, timezone
from app.core.config import settings
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SECRET_KEY = settings.JWT_SECRET_KEY
ALGORITHM = settings.JWT_ALGORITHM

security_scheme = HTTPBearer()


def create_access_token(new_id: str):
    payload = {
        "sub": str(new_id),
        "exp": datetime.now(timezone.utc) + timedelta(days=30000) # 액세스 토큰 만료 기간
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(new_id: str):
    payload = {
        "sub": str(new_id),
        "exp": datetime.now(timezone.utc) + timedelta(days=300000)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except jwt.ExpiredSignatureError:
        print("⚠️ [Auth] 토큰이 만료되었습니다.")
        return None
    except Exception as e:
        print(f"⚠️ [Auth] 토큰 검증 오류: {e}")
        return None


def get_current_user_id(res: HTTPAuthorizationCredentials = Depends(security_scheme)):
    token = res.credentials
    print(f"token : {token}")
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    return user_id
