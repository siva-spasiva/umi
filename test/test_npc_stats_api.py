import requests
import json
from app.core.security import create_access_token

token = create_access_token('test_diary_user_001')
headers = {"Authorization": f"Bearer {token}"}

res = requests.get("http://127.0.0.1:8000/api/v1/stats/NPC/bingeo", headers=headers)
print("GET bingo stats:", res.status_code)
print(json.dumps(res.json(), indent=2, ensure_ascii=False))
