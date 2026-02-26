from app.core.config import settings
from fastapi import FastAPI
from app.api.v1.user import router as user_router
from app.api.v1.chat import router as chat_router
from app.api.v1.stats import router as stats_router
from app.api.v1.inventory import router as inventory_router
from app.api.v1.health_check import router as health_router
from app.api.v1.records import router as records_router
from app.api.v1.monitoring import router as monitoring_router
from app.api.v1.conversation import router as conversation_router
from app.api.v1.debug import router as debug_router

from app.api.v1.map import router as map_router

# [New] 로그 설정 (매일 자정 logs/app.log.YYYY-MM-DD 생성)
from app.core.logger import setup_daily_rotating_logger
setup_daily_rotating_logger("api_server", "logs/app.log", capture_uvicorn=True)

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="LLM API Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For local development, allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_init_npcs():
    """
    애플리케이션 시작 시 NPC 런타임 상태를 초기화합니다.
    (이전 프로세스/세션에서 남은 메모리 상태 제거)
    """
    try:
        from app.agents.llm_engine import llm_engine
        llm_engine.reset_npc_runtime_state()
        
        import json
        import os
        from app.core.database import db
        map_path = os.path.join(os.path.dirname(__file__), "data", "map.json")
        if os.path.exists(map_path):
            with open(map_path, "r", encoding="utf-8") as f:
                map_data = json.load(f)
            await db["maps"].delete_many({})
            if map_data:
                await db["maps"].insert_many(map_data)
                print(f"✅ [Startup] Successfully seeded {len(map_data)} floors into 'maps' collection.")
        else:
            print(f"⚠️ [Startup] map.json not found at {map_path}")
            
    except Exception as e:
        print(f"⚠️ [Startup] Init failed: {e}")

app.include_router(user_router, prefix="/api/v1", tags=["user"])
app.include_router(health_router, prefix="/api/v1", tags=["system"]) # 헬스체크 등록
app.include_router(chat_router, prefix="/api/v1", tags=["chat"])
app.include_router(stats_router, prefix="/api/v1", tags=["stats"])
app.include_router(inventory_router, prefix="/api/v1/inventory", tags=["inventory"])
app.include_router(records_router, prefix="/api/v1/records", tags=["records"])
app.include_router(monitoring_router, prefix="/api/v1/monitor", tags=["monitoring"])
app.include_router(conversation_router, prefix="/api/v1", tags=["conversation"])
app.include_router(debug_router, prefix="/api/v1", tags=["debug"])
app.include_router(map_router, prefix="/api/v1/map", tags=["map"])
