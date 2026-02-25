import asyncio
from app.services.inventory_service import inventory_service
from app.schemas.inventory import InventoryResponse
from pydantic import ValidationError

async def test():
    try:
        inv = await inventory_service.get_user_inventory("test_user_123")
        print("Service returned:", inv)
        resp = InventoryResponse(**inv)
        print("Schema validation passed!")
    except ValidationError as e:
        print("Validation error:", e)

if __name__ == "__main__":
    asyncio.run(test())
