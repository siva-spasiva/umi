from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MONGODB_URL: str
    DATABASE_NAME: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str

    class Config:
        env_file = ".env"

settings = Settings()