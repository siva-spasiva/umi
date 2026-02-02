from fastapi import APIRouter, HTTPException, status
from app.schemas.chat import DayLog
from app.schemas.story import StorySummary

from app.services.chat_service import chat_service


router = APIRouter()

@router.post("/save-log")
async def save_log(log: DayLog):
    try:
        log_id = await chat_service.save_chat_log(log)
        return {"status": "success", "log_id": log_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"저장 중 오류 발생: {str(e)}")

@router.post("/summary", status_code=status.HTTP_201_CREATED)
async def create_story_summary(summary: StorySummary):
    """
    LLM이 생성한 하루치 스토리 요약 및 분석 결과를 저장합니다.
    동일한 day_index가 있으면 덮어씁니다(Upsert).
    """
    try:
        result_action = await chat_service.save_story_summary(summary)
        return {
            "status": "success",
            "action": result_action,
            "day_index": summary.day_index
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"스토리 요약 저장 중 오류 발생: {str(e)}"
        )

@router.get("/summary/{day_index}", response_model=StorySummary)
async def get_story_summary(day_index: int):
    """특정 일차의 스토리 요약 정보를 조회합니다."""
    summary = await chat_service.db["story_summaries"].find_one({"day_index": day_index})
    if not summary:
        raise HTTPException(status_code=404, detail="해당 일차의 요약 정보가 없습니다.")
    return summary