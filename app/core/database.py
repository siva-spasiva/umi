from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

class Database:
    client: AsyncIOMotorClient = None

    @classmethod
    def get_db(cls):
        if cls.client is None:
            cls.client = AsyncIOMotorClient(settings.MONGODB_URL)
        return cls.client[settings.DATABASE_NAME]

db = Database.get_db()