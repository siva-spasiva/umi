#!/usr/bin/env python3
"""
Diary API 시뮬레이션 테스트 스크립트

테스트 시나리오:
1. Day 1 설정, 4개의 세션(Session 1~4) 반복 진행
2. 각 세션마다 유저와 NPC 간 5턴의 릴레이 대화 전개 (conversation/reply)
3. 각 세션이 끝날 때마다 /end-session API를 호출하여 해당 세션 요약 및 상태 저장 진행
4. 4개의 세션이 모두 종료되면 /diary API를 호출하여 하루 일치 Diary(StorySummary) 생성
5. GET /diary/{day_index} API를 호출하여 생성된 일기를 정상적으로 불러오는지 검증
"""

import sys
import os
import asyncio
import httpx
import time
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.core.security import create_access_token
from app.core.config import settings

LOCAL_SERVER_URL = "http://localhost:8000"
TEST_USER_ID = "test_diary_user_001"
DAY_INDEX = 1

async def give_infinite_hp():
    """테스트 진행을 위해 유저에게 무한대의 HP를 지급 (MongoDB 직접 수정)"""
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.DATABASE_NAME]
    
    await db["user_stats"].update_one(
        {"user_id": TEST_USER_ID},
        {"$set": {
            "hp": 9999,
            "max_hp": 9999,
            "day_index": DAY_INDEX,
            "session_index": 1
        }},
        upsert=True
    )
    print(f"🔧 유저 {TEST_USER_ID} 에게 9999 HP 지급 완료 (Day {DAY_INDEX} 리셋).")
    client.close()

async def simulate_diary_flow():
    # 1. 테스트 유저용 인증 토큰 발급
    access_token = create_access_token(TEST_USER_ID)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # 2. HP 무한 부여
    await give_infinite_hp()

    print("\n========================================================")
    print("🚀 Diary API 시뮬레이션 테스트 시작")
    print("========================================================\n")

    async with httpx.AsyncClient(base_url=LOCAL_SERVER_URL, headers=headers, timeout=300) as client:
        # 3. 세션 1 ~ 4 반복 진행
        for session_idx in range(1, 5):
            print(f"▶️ [Day {DAY_INDEX} - Session {session_idx}] 대화 시작 (총 5턴 시뮬레이션)")
            
            history = []
            npc_id = "galchi" # 청갈치와의 대화로 고정

            # 3-1. 5턴의 릴레이 대화 진행
            for turn in range(1, 6):
                user_msg = f"세션 {session_idx}의 {turn}번째 질문이야! 교단에 대해 어떻게 생각해?"
                
                reply_payload = {
                    "topic": f"Session {session_idx} 진행중",
                    "npc_ids": [npc_id],
                    "user_message": user_msg,
                    "history": history
                }
                
                print(f"  🗣️ Turn {turn}: {user_msg}")
                start_t = time.time()
                resp = await client.post("/api/v1/conversation/reply", json=reply_payload)
                elapsed = time.time() - start_t
                
                if resp.status_code != 200:
                    print(f"  ❌ /reply 에러: {resp.text}")
                    break
                    
                data = resp.json()
                turns = data.get("turns", [])
                
                # 유저 메시지를 히스토리에 추가
                history.append({
                    "speaker": "user",
                    "speaker_id": "user",
                    "content": user_msg
                })

                # NPC 응답 출력 및 기록
                for t in turns:
                    if t.get("speaker") != "user":
                        print(f"  🤖 NPC ({elapsed:.1f}s): {t.get('content')}")
                        history.append({
                            "speaker": t.get("speaker"),
                            "speaker_id": t.get("speaker_id"),
                            "content": t.get("content")
                        })
            
            # 3-2. 세션 종료 (요약 및 장기 기억 저장 트리거)
            print(f"\n⏹️ [Session {session_idx}] 종료 요청 (/end-session)")
            end_session_payload = {
                "day_index": DAY_INDEX,
                "session_index": session_idx
            }
            resp = await client.post("/api/v1/end-session", json=end_session_payload)
            if resp.status_code == 200:
                end_data = resp.json()
                print(f"✅ Session {session_idx} 종료 (Status: {end_data.get('status')})")
                summaries = end_data.get("summaries", {})
                if summaries:
                    print("\n  [해당 세션 요약 결과]")
                    for npc, summary in summaries.items():
                        print(f"   - {npc}: {summary}")
                else:
                    print(f"  ⚠️ 요약 없음! (Message: {end_data.get('message')})")
            else:
                print(f"❌ Session {session_idx} 종료 에러: {resp.text}")
                
            print("\n" + "-" * 50)

        # 4. 4개 세션 종료 후 Diary(하루 요약) 자동 생성 트리거
        print("\n========================================================")
        print("✍️ 모든 세션 종료. 하루 요약(Diary) 생성 중 (/diary)")
        print("========================================================")
        
        diary_payload = {"day_index": DAY_INDEX}
        start_t = time.time()
        diary_resp = await client.post("/api/v1/diary", json=diary_payload)
        elapsed = time.time() - start_t
        
        if diary_resp.status_code == 201 or diary_resp.status_code == 200:
            print(f"✅ Diary 생성 완료 ({elapsed:.1f}s)")
        else:
            print(f"❌ Diary 생성 에러: {diary_resp.text}")

        # 5. 생성된 Diary 조회 (GET API 테스트)
        print("\n========================================================")
        print(f"🔍 생성된 일기 조회 (GET /diary/{DAY_INDEX})")
        print("========================================================")
        
        get_resp = await client.get(f"/api/v1/diary/{DAY_INDEX}")
        if get_resp.status_code == 200:
            diary_data = get_resp.json()
            print("✅ Diary 조회 성공!\n")
            print(f"📅 대상 날짜: Day {diary_data.get('day_index')}")
            
            diary = diary_data.get('diary', {})
            print(f"📝 제목: {diary.get('title')}")
            print(f"📝 메인 요약 (Tone: {diary.get('tone')}):\n{diary.get('text')}")
            
            print("\n🔹 주요 요약 포인트:")
            for bullet in diary_data.get("summary_bullets", []):
                print(f" - {bullet}")
                
            print("\n🎒 획득/사용 아이템 내역:")
            for item in diary_data.get("items", []):
                print(f" - {item.get('name')}: {item.get('how_used_or_implication')}")
                
            print("\n🔑 주요 대화:")
            for conv in diary_data.get("key_conversations", []):
                print(f" - [{conv.get('with')}]: {conv.get('what_changed')} (\"{conv.get('quote')}\")")
        else:
            print(f"❌ Diary 조회 에러: {get_resp.status_code} - {get_resp.text}")

if __name__ == "__main__":
    asyncio.run(simulate_diary_flow())
