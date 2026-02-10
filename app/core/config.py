import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    MONGODB_URL: str
    DATABASE_NAME: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str

    # AI Model Paths (.env에 정의된 경로들)
    GA1_MODEL_PATH: Optional[str] = None
    GA2_MODEL_PATH: Optional[str] = None
    STORY_MODEL_PATH: Optional[str] = None
    NPC_MODEL_PATH: Optional[str] = None

    # AI Options
    USE_OLLAMA: bool = False
    OLLAMA_URL: Optional[str] = None
    OLLAMA_MODEL: Optional[str] = None
    USE_MLX: bool = False

    # LangSmith Settings
    LANGCHAIN_TRACING_V2: str = "false"
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGCHAIN_API_KEY: Optional[str] = None
    LANGCHAIN_PROJECT: Optional[str] = None

    class Config:
        env_file = ".env"
        extra = "ignore"  # 정의되지 않은 변수가 .env에 있어도 에러 무시

# .env 파일을 시스템 환경 변수로 즉시 로드 (LangSmith 등 외부 라이브러리 인식용)
load_dotenv()

settings = Settings()

# LangSmith 등 외부 라이브러리가 os.environ을 직접 참조하는 경우를 위해 동기화
if settings.LANGCHAIN_TRACING_V2:
    os.environ["LANGCHAIN_TRACING_V2"] = settings.LANGCHAIN_TRACING_V2
if settings.LANGCHAIN_API_KEY:
    os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
if settings.LANGCHAIN_PROJECT:
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT