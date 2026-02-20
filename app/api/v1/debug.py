from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.agents.llm_engine import llm_engine

router = APIRouter()

class SetStateRequest(BaseModel):
    npc_id: str
    friendly: int = Field(..., ge=0, le=100)
    faith: int = Field(..., ge=0, le=100)

@router.post("/debug/set_npc_state")
async def set_npc_state(request: SetStateRequest):
    """
    [DEBUG] NPC 상태 강제 설정
    테스트 목적으로 특정 NPC의 친밀도/신뢰도를 변경합니다.
    """
    try:
        llm_engine.set_npc_state(request.npc_id, request.friendly, request.faith)
        return {"status": "success", "npc_id": request.npc_id, "friendly": request.friendly, "faith": request.faith}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
