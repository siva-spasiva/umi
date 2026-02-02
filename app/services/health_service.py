import re
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

class HealthService:
    def __init__(self):
        self.client = AsyncIOMotorClient(settings.MONGODB_URL)
        self.db = self.client[settings.DATABASE_NAME]
        self.collection = self.db["messages"]

health_service = HealthService()