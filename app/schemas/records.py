from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime

class Recording(BaseModel):
    """녹음 파일 정보 (메타데이터 + 내용)"""
    record_id: str
    user_id: str
    title: Optional[str] = None
    messages: List[Dict[str, Any]]
    created_at: datetime

class SaveRecordingRequest(BaseModel):
    """대화 녹음 저장 요청"""
    messages: List[Dict[str, Any]]
    title: Optional[str] = None

class RecordingListResponse(BaseModel):
    """녹음 목록 응답용 (내용 제외 가능)"""
    record_id: str
    title: Optional[str] = None
    created_at: datetime