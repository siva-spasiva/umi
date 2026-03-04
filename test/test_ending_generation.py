import sys
import os
import asyncio
import httpx
import uuid
import json
from datetime import datetime

# 프로젝트 최상단 경로를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.core.security import get_current_user_id
from app.core.database import db

# 테스트 데이터 유저 ID
test_user_id = f"ending_user_{uuid.uuid4().hex[:8]}"
print(f"Test User ID: {test_user_id}")

# StoryAgent.generate를 모킹하여 LLM 호출 없이 테스트 진행 (서버 환경 영향 배제)
import unittest.mock as mock
from app.agents.story_agent import story_agent

async def mock_generate(prompt, **kwargs):
    # EPILOGUE 모드 요청인지 확인
    if "EPILOGUE" in prompt:
        return '{ "title": "최종 진실", "text": "조사는 충격적인 발견과 함께 끝을 맺습니다.", "ending_type": "exposed", "reason": "체계적인 증거 수집 덕분입니다." }'
    return '{ "diary": { "title": "샘플 제목", "text": "샘플 내용", "tone": "차분함" }, "summary_bullets": [], "key_conversations": [], "items": [], "clues": [], "troll_level_analysis": {"delta_total": 0, "top_causes": []}, "consistency_check": {"contradictions_found": [], "missing_info": []}, "ending": {"status": "continue", "ending_type": "null", "reason": "", "required_next_step": ""}, "flags_for_next_day": [], "safety": {"hallucination_risk": "low", "spoiler_blocked": true} }'

story_agent.generate = mock.AsyncMock(side_effect=mock_generate)

# [설정 강제 변경] 로컬 모델 테스트를 위해 GPU Proxy 비활성화 (필요 시)
from app.core.config import settings
settings.USE_GPU_PROXY = False

# [인증 우회]
def mock_get_current_user_id() -> str:
    return test_user_id

app.dependency_overrides[get_current_user_id] = mock_get_current_user_id

async def seed_mock_diaries():
    """1일차의 mock 일기 데이터 MongoDB에 삽입 (테스트 단순화)"""
    print(f"🔄 [Setup] Mock 일기 데이터 생성 중 (User: {test_user_id})...")
    mock_diaries = []
    for i in range(1, 2):  # 1일만 생성
        mock_diaries.append({
            "user_id": test_user_id,
            "day_index": i,
            "diary": {
                "title": f"Day {i} Investigation",
                "text": f"This is the investigation record for day {i}. Found some clues about the cult.",
                "tone": "investigative"
            },
            "summary_bullets": [f"Clue {i} discovered"],
            "key_conversations": [],
            "items": [],
            "clues": [],
            "troll_level_analysis": {"delta_total": 0, "top_causes": []},
            "consistency_check": {"contradictions_found": [], "missing_info": []},
            "ending": {"status": "continue", "ending_type": "null", "reason": "", "required_next_step": ""},
            "flags_for_next_day": [],
            "safety": {"hallucination_risk": "low", "spoiler_blocked": True},
            "time": datetime.now()
        })
    
    await db["story_diary"].insert_many(mock_diaries)
    print("✅ [Setup] Mock 일기 1~5일차 삽입 완료")

async def test_generate_ending():
    """엔딩 생성 API 호출 테스트"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        print("\n🚀 [Test] 엔딩 생성(POST /api/v1/ending) 테스트 시작...")
        response = await client.post("/api/v1/ending")
        assert response.status_code == 200, f"API 호출 실패: {response.text}"
        data = response.json()
        
        # 응답 구조 확인
        assert "user_id" in data
        assert "title" in data
        assert "text" in data
        assert "ending_type" in data
        assert "reason" in data
        
        print("\n--- Generated Ending ---")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print("------------------------")
        
        # 결과를 JSON 파일로 저장
        result_path = os.path.join(os.path.dirname(__file__), "test_ending_result.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"📁 결과가 파일로 저장되었습니다: {result_path}")
        
        print("✅ Test 1: 엔딩 생성 및 스키마 검증 완료")

async def test_get_epilogue():
    """저장된 에필로그 조회 테스트"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        print("\n🚀 [Test] 에필로그 조회(GET /api/v1/epilogue) 테스트 시작...")
        response = await client.get("/api/v1/epilogue")
        assert response.status_code == 200
        data = response.json()
        
        assert data["user_id"] == test_user_id
        print(f"✅ Test 2: 저장된 에필로그 조회 완료 (Title: {data['title']})")

async def main():
    try:
        await seed_mock_diaries()
        await test_generate_ending()
        await test_get_epilogue()
        print("\n🎉 모든 엔딩 시스템 테스트 통과!")
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 테스트 데이터 삭제 (선택 사항)
        print("\n🧹 [Cleanup] 테스트 데이터 삭제 중...")
        await db["story_diary"].delete_many({"user_id": test_user_id})
        await db["game_endings"].delete_many({"user_id": test_user_id})
        print("✅ [Cleanup] 완료")

if __name__ == "__main__":
    asyncio.run(main())
