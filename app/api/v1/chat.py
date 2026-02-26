from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from app.schemas.chat import DayLog, ChatRequest, ChatResponse
from app.schemas.story import StorySummary, EpilogueResponse

from app.services.chat_service import chat_service
from app.services.conversation_service import conversation_service
from app.agents.llm_engine import llm_engine
from app.core.security import get_current_user_id
from app.core.database import db
from app.services.stats_service import stats_service

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
    HP 10을 소모합니다.
    """
    # HP 소모 (10)
    hp_result = await stats_service.spend_hp(user_id, 10, "NPC 대화")
    if not hp_result["success"]:
        raise HTTPException(status_code=400, detail=hp_result["message"])

    result = await chat_service.process_chat_flow(user_id, request.npcId, request.message, request.item_id)
    
    if result.get("status") == "blocked_by_guardrail":
        return {"response": result["response"], "blocked": True}
        
    result["hp"] = hp_result
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
    summary = await chat_service.db["story_diary"].find_one({"day_index": day_index, "user_id": user_id})
    if not summary:
        raise HTTPException(status_code=404, detail="해당 일차의 요약 정보가 없습니다.")
    return summary


@router.get("/diary/{day_index}", response_model=StorySummary,
            summary="특정 일차 일기 조회",
            description="지정한 날짜(day_index)에 생성된 일기(StorySummary)를 조회합니다. 현재 /summary API와 동일한 DB 컬렉션을 바라봅니다."
            )
async def get_diary(day_index: int, user_id: str = Depends(get_current_user_id)):
    """특정 일차의 일기(요약)를 조회합니다."""
    # 내부적으로 summary와 diary는 동일한 story_diary 컬렉션을 사용합니다.
    diary = await chat_service.db["story_diary"].find_one({"day_index": day_index, "user_id": user_id})
    if not diary:
        raise HTTPException(status_code=404, detail="해당 일차의 일기 정보가 없습니다.")
    return diary

class EndSessionRequest(BaseModel):
    """세션 종료 요청"""
    day_index: int
    session_index: int = Field(..., ge=1, le=4)


@router.post("/end-session",
             summary="세션 종료 — 대화 내용 저장",
             description="NPC와의 대화 세션을 종료합니다. 대화를 요약하여 장기 기억(Vector DB)에 저장하고 버퍼를 비웁니다. 다음 세션(또는 다음 날)으로 넘어가기 전에 호출합니다."
             )
async def end_session(request: EndSessionRequest, user_id: str = Depends(get_current_user_id)):
    """
    대화 세션 종료:
    - Day 0 (튜토리얼): 실제 로직 없이 day/session만 전환
    - Day 1+: 대화 요약 → 장기 기억 저장 → 다음 세션 맵 생성
    - day_index : 실제 존재하는 게임 내 일차( 1-5)
    - session_index : 일차 내 세션 인덱스 (1-4)
    """
    # Day 0 (튜토리얼): 게임 로직 없이 세션만 전환
    if request.day_index == 0:
        advance_result = await stats_service.advance_session(user_id)
        return {
            "status": "tutorial",
            "message": "튜토리얼 세션입니다. 게임 데이터는 저장되지 않습니다.",
            "day_index": request.day_index,
            "session_index": request.session_index,
            "advance": advance_result,
        }

    if request.day_index > 5:
        raise HTTPException(status_code=400, detail="day_index는 최대 5일까지만 가능합니다.")
        
    if request.session_index > 4:
        raise HTTPException(status_code=400, detail="session_index는 최대 4(하루 4세션)까지만 가능합니다.")
        
    if request.session_index == 4:
        # TODO: 하루의 마지막(4번째) 세션이 종료되었습니다. 다음 날(day)로 넘어가는 처리/초기화 로직을 여기에 작성해야 합니다.
        pass

    try:
        summaries = await llm_engine.save_session_summary(request.day_index, None, user_id)
        
        # [NEW] 다음 세션 계산 및 맵(NPC 위치 및 주제) 설정
        from app.services.schedule_service import schedule_service
        from app.core.database import db
        next_day, next_session = schedule_service.get_next_session_info(request.day_index, request.session_index)
        next_map_config = await schedule_service.generate_map_config(next_day, next_session)
        
        # [NEW] 다음 세션 맵 상태를 MongoDB에 저장 (room API에서 읽어감)
        await db["session_map_state"].update_one(
            {"day_index": next_day, "session_index": next_session},
            {"$set": next_map_config},
            upsert=True
        )

        advance_result = await stats_service.advance_session(user_id)
        
        # [NEW] 세션 전환 후 유저 위치 강제 이동
        # next_session에 따라 위치 설정
        # 1: B2/room001, 2: B1/cafeteria, 3: B3/truth_room001, 4: B3/chapel
        location_map = {
            1: {"floor_id": "B2", "room_id": "room001"},
            2: {"floor_id": "B1", "room_id": "cafeteria"},
            3: {"floor_id": "B3", "room_id": "truth_room001"},
            4: {"floor_id": "B3", "room_id": "chapel"}
        }
        
        if next_session in location_map:
            loc = location_map[next_session]
            await stats_service.update_stats(loc, user_id)
            # update advance_result to reflect new location if needed by client, though typical client re-fetches stats
        
        if not summaries:
            return {
                "status": "skipped",
                "message": "대화 내역이 없어 요약을 생략했습니다.",
                "day_index": request.day_index,
                "session_index": request.session_index,
                "next_session_map": next_map_config,
                "advance": advance_result,
            }
        
        return {
            "status": "success",
            "day_index": request.day_index,
            "session_index": request.session_index,
            "summaries": summaries,
            "next_session_map": next_map_config,
            "advance": advance_result,
        }
    except Exception as e:
        print(f"[ERROR] end-session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"세션 요약 저장 중 오류 발생: {str(e)}"
        )


@router.post("/ending", response_model=EpilogueResponse,
             summary="최종 엔딩(에필로그) 생성 및 조회",
             description="1~5일차의 모든 일기를 분석하여 게임의 최종 엔딩을 생성합니다. 5일차 일기 생성 후 자동으로 호출되기도 하지만, 수동으로 재생성하거나 조회할 때 사용합니다."
             )
async def generate_game_ending(user_id: str = Depends(get_current_user_id)):
    """최종 엔딩 생성 API"""
    try:
        return await chat_service.create_ending(user_id)
    except Exception as e:
        print(f"[ERROR] generate-ending: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"엔딩 생성 중 오류 발생: {str(e)}"
        )


@router.get("/epilogue", response_model=EpilogueResponse,
            summary="저장된 엔딩 조회",
            description="이미 생성되어 저장된 최종 엔딩 데이터를 조회합니다."
            )
async def get_game_epilogue(user_id: str = Depends(get_current_user_id)):
    """저장된 엔딩 조회 API"""
    ending = await chat_service.db["game_endings"].find_one({"user_id": user_id})
    if not ending:
        raise HTTPException(status_code=404, detail="생성된 엔딩이 없습니다. /ending을 먼저 호출하세요.")
    return ending


class EavesdropRequest(BaseModel):
    """추가 엿듣기 요청 — 방 정보만 넘기면 서버가 알아서 처리"""
    day_index: int = Field(..., description="현재 게임 일차")
    session_index: int = Field(..., description="현재 세션 인덱스")
    room_id: str = Field(..., description="엿듣기 중인 방 ID")


@router.post("/eavesdrop", summary="추가 엿듣기",
             description="NPC 대화를 추가로 엿듣습니다. HP 5를 소모합니다.")
async def eavesdrop_more(request: EavesdropRequest, user_id: str = Depends(get_current_user_id)):
    """추가 엿듣기 API (HP -5)"""
    # HP 소모 (5)
    hp_result = await stats_service.spend_hp(user_id, 5, "엿듣기")
    if not hp_result["success"]:
        raise HTTPException(status_code=400, detail=hp_result["message"])

    session_state = await db["session_map_state"].find_one(
        {"day_index": request.day_index, "session_index": request.session_index},
        {"_id": 0}
    )
    
    if not session_state:
        raise HTTPException(status_code=404, detail="해당 세션의 맵 정보가 없습니다.")
    
    room_placement = None
    for placement in session_state.get("room_placements", []):
        if placement.get("room_id") == request.room_id:
            room_placement = placement
            break
    
    if not room_placement or len(room_placement.get("npcs", [])) < 2 or not room_placement.get("topic"):
        raise HTTPException(status_code=404, detail="이 방에서 엿들을 수 있는 대화가 없습니다.")
    
    topic_data = room_placement["topic"]
    topic_text = f"{topic_data.get('title', '')}: {topic_data.get('context', '')}"
    npc_ids_lower = [npc.lower() for npc in room_placement["npcs"]]
    
    try:
        conversation = await conversation_service.start_auto_conversation(
            topic=topic_text,
            npc_ids=npc_ids_lower,
            num_turns=6
        )
        return {
            "conversation": conversation.model_dump(),
            "can_eavesdrop_more": True
        }
    except Exception as e:
        print(f"[ERROR] eavesdrop: {e}")
        raise HTTPException(status_code=500, detail=f"엿듣기 생성 중 오류: {str(e)}")
