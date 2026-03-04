import uuid
from datetime import datetime
from app.services.base_service import BaseService
from app.core.security import create_access_token, verify_token, create_refresh_token

class UserService(BaseService):
    def __init__(self):
        super().__init__()
        self.collection_token = self.db["tokens"]
        self.collection_user_state = self.db["user_states"]

    async def login_anonymous(self):
        """
        익명 로그인: 새로운 사용자 ID 생성 및 토큰 발급
        """
        user_id = str(uuid.uuid4())
        access_token = create_access_token(user_id)
        refresh_token = create_refresh_token(user_id)
        
        # 기본 유저 상태 생성 (선택사항, 필요시 추가)
        # await self.collection_user_state.insert_one({"user_id": user_id, ...})
        
        # 토큰 정보 저장 (유효성 검증용)
        await self.collection_token.insert_one({
            "user_id": user_id,
            "refresh_token": refresh_token,
            "created_at": datetime.now()
        })

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }

    async def refresh_session_token(self, refresh_token: str):
        """리프레시 토큰을 검증하고 새로운 액세스 토큰을 발급합니다."""
        user_id = verify_token(refresh_token)
        if not user_id:
            return None

        # DB에 저장된 리프레시 토큰인지 확인
        token_record = await self.collection_token.find_one({
            "user_id": user_id, 
            "refresh_token": refresh_token
        })
        
        if not token_record:
            return None

        new_access_token = create_access_token(user_id)

        return {
            "access_token": new_access_token,
            "refresh_token": refresh_token, # 기존 리프레시 토큰 유지
            "token_type": "bearer"
        }

user_service = UserService()
