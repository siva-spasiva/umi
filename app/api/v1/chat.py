from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from app.schemas.chat import DayLog, ChatRequest, ChatResponse
from app.schemas.story import StorySummary

from app.services.chat_service import chat_service
from app.agents.llm_engine import llm_engine
from app.core.security import get_current_user_id

from typing import Optional

router = APIRouter()


class EndDayRequest(BaseModel):
    """하루 종료 요청"""
    day_index: int
    npc_id: Optional[str] = None


@router.post("/chat", summary="NPC와 대화 (가드레일 적용)")
async def chat_with_npc(request: ChatRequest, user_id: str = Depends(get_current_user_id)):
    """
    GA 에이전트가 입력과 출력을 검증하는 채팅 API입니다.
    """
    result = await chat_service.process_chat_flow(user_id, request.npcId, request.message, request.item_id)
    
    if result.get("status") == "blocked_by_guardrail":
        return {"response": result["response"], "blocked": True}
        
    return result

@router.post(
    "/save-log",
    summary="대화 로그 저장",
    description="유저와 NPC 간의 원본 대화 로그를 저장합니다. 일자별 대화 흐름 파악에 사용됩니다."
)
async def save_log(log: DayLog):
    try:
        log_id = await chat_service.save_chat_log(log)
        return {"status": "success", "log_id": log_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"저장 중 오류 발생: {str(e)}")


@router.post("/summary", status_code=status.HTTP_201_CREATED,
             summary="스토리 요약 저장",
             description="LLM이 분석한 하루치 스토리 요약, 획득 아이템, 주요 이벤트를 저장합니다. 동일한 날짜가 있으면 덮어씁니다."
             )
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


class DiaryGenerationRequest(BaseModel):
    day_index: Optional[int] = None

@router.post("/diary", status_code=status.HTTP_201_CREATED,
             summary="일기 생성 (서버 측 자동 분석)",
             description="서버에 저장된 대화 로그를 기반으로 LLM이 하루를 분석하여 일기(StorySummary)를 생성하고 저장합니다."
             )
async def generate_diary(request: DiaryGenerationRequest, user_id: str = Depends(get_current_user_id)):
    """
    일기 생성 API
    - day_index를 지정하면 해당 날짜의 로그를 기반으로 생성합니다.
    - 지정하지 않으면 현재 진행 중인 날짜를 자동 계산합니다.
    """
    try:
        summary_result = await chat_service.create_diary_entry(user_id, request.day_index)
        return {
            "status": "success",
            "day_index": summary_result.day_index,
            "data": summary_result
        }
    except Exception as e:
        print(f"[ERROR] Generate Diary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"일기 생성 중 오류 발생: {str(e)}"
        )


@router.get("/summary/{day_index}", response_model=StorySummary,
            summary="특정 일차 스토리 요약 조회",
            description="지정한 날짜(day_index)의 스토리 요약 및 분석 결과를 조회합니다."
            )
async def get_story_summary(day_index: int, user_id: str = Depends(get_current_user_id)):
    """특정 일차의 스토리 요약 정보를 조회합니다."""
    # [REFACTOR] story_summaries -> story_diary
    summary = await chat_service.db["story_diary"].find_one({"day_index": day_index})
    if not summary:
        raise HTTPException(status_code=404, detail="해당 일차의 요약 정보가 없습니다.")
    return summary


class EndSessionRequest(BaseModel):
    """세션 종료 요청"""
    day_index: int
    session_index: int
    npc_id: Optional[str] = None


@router.post("/end-session",
             summary="세션 종료 — 대화 내용 저장",
             description="NPC와의 대화 세션을 종료합니다. 대화를 요약하여 장기 기억(Vector DB)에 저장하고 버퍼를 비웁니다. 다음 세션(또는 다음 날)으로 넘어가기 전에 호출합니다."
             )
async def end_session(request: EndSessionRequest, user_id: str = Depends(get_current_user_id)):
    """
    대화 세션 종료:
    - 현재까지의 대화 내용을 요약하여 장기 기억에 저장합니다.
    - session_summary 타입으로 저장됩니다.
    
    - day_index: 게임 내 일차 (1~5)
    - session_index: 일차 내 세션 인덱스 (1~4)
    - npc_id: NPC 식별자 (선택 사항. 생략 시 현재 세션 버퍼가 있는 모든 NPC 처리)
    """
    if request.day_index > 5:
        raise HTTPException(status_code=400, detail="day_index는 최대 5일까지만 가능합니다.")
        
    if request.session_index > 4:
        raise HTTPException(status_code=400, detail="session_index는 최대 4(하루 4세션)까지만 가능합니다.")
        
    if request.session_index == 4:
        # TODO: 하루의 마지막(4번째) 세션이 종료되었습니다. 다음 날(day)로 넘어가는 처리/초기화 로직을 여기에 작성해야 합니다.
        pass

    try:
        summaries = await llm_engine.save_session_summary(request.day_index, request.npc_id, user_id)
        
        if not summaries:
            return {
                "status": "skipped",
                "message": "대화 내역이 없어 요약을 생략했습니다.",
                "day_index": request.day_index,
                "session_index": request.session_index
            }
        
        return {
            "status": "success",
            "day_index": request.day_index,
            "session_index": request.session_index,
            "summaries": summaries
        }
    except Exception as e:
        print(f"[ERROR] end-session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"세션 요약 저장 중 오류 발생: {str(e)}"
        )
