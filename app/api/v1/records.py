from fastapi import APIRouter, Depends, HTTPException
from typing import List
from app.schemas.records import Recording, SaveRecordingRequest, RecordingListResponse
from app.services.record_service import record_service
from app.core.security import get_current_user_id

router = APIRouter()

@router.post("", summary="대화 녹음 저장")
async def save_recording(data: SaveRecordingRequest, user_id: str = Depends(get_current_user_id)):
    """현재 진행 중인 대화 리스트를 'records' 컬렉션에 고유 ID와 함께 저장합니다."""
    record_id = await record_service.save_recording(user_id, data.messages, data.title)
    return {"status": "success", "record_id": record_id}

@router.get("/list", response_model=List[RecordingListResponse], summary="녹음 목록 조회")
async def get_recording_list(user_id: str = Depends(get_current_user_id)):
    """유저가 저장한 모든 녹음 파일의 목록을 가져옵니다. (대화 내용은 제외되어 가볍게 응답합니다)"""
    return await record_service.get_user_recordings(user_id)

@router.get("/{record_id}", response_model=Recording, summary="특정 녹음 상세 조회")
async def get_recording(record_id: str, user_id: str = Depends(get_current_user_id)):
    """특정 녹음 ID에 해당하는 전체 대화 리스트와 상세 정보를 조회합니다."""
    recording = await record_service.get_recording(user_id, record_id)
    if not recording:
        raise HTTPException(status_code=404, detail="녹음 파일을 찾을 수 없습니다.")
    return recording