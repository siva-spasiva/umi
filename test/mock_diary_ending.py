import asyncio
from app.core.database import db

async def mock_test():
    user_id = "test_diary_user_001"
    
    # Clear old data
    await db["story_diary"].delete_many({"user_id": user_id})
    await db["game_endings"].delete_many({"user_id": user_id})
    
    # 2. Insert a rich mock diary
    mock_diary = {
        "user_id": user_id,
        "day_index": 1,
        "diary": {
            "title": "첫 번째 단서",
            "text": "오늘 교단 지하에서 이상한 의식을 목격했다. 무언가 큰 비밀이 숨겨져 있는 것이 틀림없다."
        },
        "items": [
            {"name": "낡은 열쇠", "how_used_or_implication": "지하 예배당의 굳게 닫힌 문을 여는 데 사용했다."},
            {"name": "찢어진 일기장", "how_used_or_implication": "과거 실종된 신도들이 모종의 약물 실험을 당했다는 정황을 파악했다."}
        ],
        "key_conversations": [
            {"with": "곽빙어", "what_changed": "처음엔 경계했지만 지속적인 대화 끝에 솔피의 정체에 대해 의구심을 표출했다.", "quote": "그분이 정말 우리를 구원하실까...?"},
            {"with": "솔피", "what_changed": "직접적인 대화에서 강압적이고 위압적인 태도를 보이며 복종을 강요했다.", "quote": "의심은 곧 파멸이다."}
        ],
        "clues": [
            {"info": "매일 밤 12시에 기도실에서 이상한 소음이 발생한다.", "importance": "high"}
        ]
    }
    
    await db["story_diary"].insert_one(mock_diary)
    print("Mock DB insertion complete.")

if __name__ == "__main__":
    asyncio.run(mock_test())
