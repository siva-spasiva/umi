# [중요] 환경 변수 설정을 위해 config를 가장 먼저 임포트합니다.
from app.core.config import settings
from fastapi import FastAPI
from app.api.v1.chat import router as chat_router
from app.api.v1.stats import router as stats_router
from app.api.v1.inventory import router as inventory_router
from app.api.v1.health_check import router as health_router
from app.api.v1.records import router as records_router
from app.api.v1.monitoring import router as monitoring_router
from app.api.v1.conversation import router as conversation_router

app = FastAPI(title="LLM API Server")

app.include_router(health_router, prefix="/api/v1", tags=["system"]) # 헬스체크 등록
app.include_router(chat_router, prefix="/api/v1", tags=["chat"])
app.include_router(stats_router, prefix="/api/v1", tags=["stats"])
app.include_router(inventory_router, prefix="/api/v1/inventory", tags=["inventory"])
app.include_router(records_router, prefix="/api/v1/records", tags=["records"])
app.include_router(monitoring_router, prefix="/api/v1/monitor", tags=["monitoring"])
app.include_router(conversation_router, prefix="/api/v1", tags=["conversation"])