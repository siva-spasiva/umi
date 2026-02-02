from fastapi import FastAPI
from app.api.v1.chat import router as chat_router
from app.api.v1.health_check import router as health_router
from app.services.chat_service import chat_service

app = FastAPI(title="LLM API Server")

@app.on_event("startup")
async def startup_db_client():
    try:
        await chat_service.client.admin.command('ping')
        print("🚀 MongoDB Connected Successfully!")
    except Exception as e:
        print(f"❌ DB Connection Failed: {e}")

app.include_router(health_router, prefix="/api/v1", tags=["system"]) # 헬스체크 등록
app.include_router(chat_router, prefix="/api/v1", tags=["chat"])