from fastapi import APIRouter
from app.services.health_service import health_service

router = APIRouter()

@router.get("/health")
async def health_check():
    # 1. DB 연결 상태 확인
    try:
        # MongoDB에 핑을 날려 응답 시간 확인
        await health_service.db.command("ping")
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    return {
        "status": "ok" if db_status == "healthy" else "error",
        "components": {
            "server": "running",
            "database": db_status
        }
    }
