import asyncio
import json
from httpx import AsyncClient
from app.main import app
from app.core.security import create_access_token

async def test_npc_to_npc_conversation():
    # 1. 테스트용 인증 토큰 생성
    test_user_id = "test_user_001"
    access_token = create_access_token(data={"sub": test_user_id, "role": "user"})
    headers = {"Authorization": f"Bearer {access_token}"}

    async with AsyncClient(app=app, base_url="http://test") as client:
        # =====================================================================
        # [방법 1] /api/v1/conversation/start 를 이용한 NPC 자동 대화 (추천)
        # =====================================================================
        print("=== [방법 1] /api/v1/conversation/start (NPC 끼리 알아서 대화) ===")
        start_payload = {
            "topic": "오늘 저녁 식단에 대해",
            "npc_ids": ["NPC_KWAK_01", "NPC_CHEONG_02"],
            "num_turns": 4
        }
        
        response = await client.post(
            "/api/v1/conversation/start", 
            json=start_payload, 
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()[0]
            for turn in data["turns"]:
                print(f"{turn['speaker']}: {turn['content']}")
        else:
            print("Start API Error:", response.text)

        print("\n" + "="*50 + "\n")

        # =====================================================================
        # [방법 2] /api/v1/conversation/reply 를 응용한 릴레이 대화 테스트
        # =====================================================================
        # 주의: /reply API는 기본적으로 요청의 주체가 'user(유저)'라고 하드코딩 되어 있습니다.
        # NPC가 유저에게 말을 거는 상황을 시뮬레이션하거나, 
        # API 로직을 뜯어고치지 않는 이상 완벽한 NPC-to-NPC는 start API가 맞습니다.
        print("=== [방법 2] /api/v1/conversation/reply (유저 개입 릴레이) ===")
        
        # 이전 히스토리 모의 데이터
        history_data = [
            {"speaker": "NPC_KWAK_01", "speaker_id": "NPC_KWAK_01", "content": "요즘 바다가 영 심상치 않지 않아?"}
        ]
        
        reply_payload = {
            "topic": "바다의 이상 징후",
            "npc_ids": ["NPC_CHEONG_02"], # 청갈치 혼자 대답하게 함
            "user_message": "글쎄, 나는 잘 모르겠는데 넌 어때?", # 유저(또는 다른 NPC인 척)의 발언
            "history": history_data
        }
        
        response = await client.post(
            "/api/v1/conversation/reply", 
            json=reply_payload, 
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            for turn in data["turns"]:
                print(f"{turn['speaker']}: {turn['content']}")
        else:
            print("Reply API Error:", response.text)


if __name__ == "__main__":
    asyncio.run(test_npc_to_npc_conversation())
