from fastapi.testclient import TestClient
from app.main import app
from app.core.security import get_current_user_id

# FastAPI의 TestClient를 사용하면 서버를 실제로 띄우지 않고도 요청을 보낼 수 있습니다.
client = TestClient(app)

# [인증 우회] 테스트를 위해 가짜 유저 ID를 주입합니다.
def mock_get_current_user_id():
    return "test_user_123"

# 앱의 의존성(Dependency)을 가짜 함수로 덮어씌웁니다.
app.dependency_overrides[get_current_user_id] = mock_get_current_user_id

def test_health_check():
    """헬스 체크 API가 정상 작동하는지 확인"""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    print("\n✅ 헬스 체크 통과")