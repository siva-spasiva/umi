import requests
import json
from app.core.security import create_access_token

token = create_access_token('test_diary_user_001')
headers = {"Authorization": f"Bearer {token}"}

payload = {
    "message": "안녕하세요, 오늘 무슨 일 있으세요?",
    "npcId": "bingeo",
    "item_id": None
}

res = requests.post("http://127.0.0.1:8000/api/v1/chat", headers=headers, json=payload)
print(json.dumps(res.json(), indent=2, ensure_ascii=False))
