import asyncio
import os
import sys
from unittest.mock import MagicMock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.schedule_service import schedule_service


class _DummyCursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, length=100):
        return self.rows


async def main():
    original_collection = schedule_service.schedule_collection
    try:
        rows = [
            {
                "npc_id": "npc_none",
                "schedule": {"default": {"morning": None}}
            },
            {
                "npc_id": "npc_null_str",
                "schedule": {"default": {"morning": "null"}}
            },
            {
                "npc_id": "npc_empty",
                "schedule": {"default": {"morning": ""}}
            },
            {
                "npc_id": "npc_valid",
                "schedule": {"default": {"morning": "cafeteria"}}
            }
        ]

        fake_collection = MagicMock()
        fake_collection.find.return_value = _DummyCursor(rows)
        schedule_service.schedule_collection = fake_collection

        grouped = await schedule_service.map_npc_locations(day=1, session=1)
        print("grouped:", grouped)

        assert "cafeteria" in grouped
        assert grouped["cafeteria"] == ["npc_valid"]
        assert "null" not in grouped
        assert "" not in grouped

        print("✅ null/empty room_id는 배치 제외됨")
    finally:
        schedule_service.schedule_collection = original_collection


if __name__ == "__main__":
    asyncio.run(main())
