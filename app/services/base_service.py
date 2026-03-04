from app.core.database import db

class BaseService:
    def __init__(self):
        self.db = db