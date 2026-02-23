"""
=============================================================
HP Management Test (HP 소모 & 시간대 전환 통합 테스트)
=============================================================

테스트 시나리오:
1. 유저 초기화 (HP 100, morning, Day 1)
2. 같은 시간대 내 소모 (HP 100→90, morning 유지)
3. plusHp 부여 후 우선 소모 확인
4. 시간대 경계 돌파 (morning → afternoon)
5. 추가 소모로 evening 전환
6. 대량 소모로 night 전환
7. HP 고갈 → 다음 날 전환 (Day 1→2, HP 리셋)
8. 체력 부족 시 실패 확인
9. 프리뷰 API 검증
10. hp_events DB 히스토리 검증
"""

import sys
import os
import asyncio
import uuid
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from app.main import app
from app.core.security import get_current_user_id
from app.core.database import db
from app.core.config import settings

# ── 인증 우회 ──
test_user_id = f"hp_test_{uuid.uuid4().hex[:8]}"

def mock_get_current_user_id() -> str:
    return test_user_id

app.dependency_overrides[get_current_user_id] = mock_get_current_user_id


async def main():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        passed = 0
        failed = 0
        total_tests = 0
        
        def check(name: str, condition: bool, detail: str = ""):
            nonlocal passed, failed, total_tests
            total_tests += 1
            if condition:
                passed += 1
                print(f"  ✅ {name}")
            else:
                failed += 1
                print(f"  ❌ {name} → {detail}")
        
        try:
            # ══════════════════════════════════════════════
            # Step 1: 유저 초기화
            # ══════════════════════════════════════════════
            print("\n" + "="*60)
            print("📌 Step 1: 유저 초기화")
            print("="*60)
            
            resp = await client.post("/api/v1/users/login")
            assert resp.status_code == 200
            
            resp = await client.get("/api/v1/stats/static")
            assert resp.status_code == 200
            print(f"  유저 생성 완료: {test_user_id}")
            print(f"  초기 스탯: HP=100, period=morning, day=1")

            # ══════════════════════════════════════════════
            # Step 2: 같은 시간대 내 소모 (morning 유지)
            # ══════════════════════════════════════════════
            print("\n" + "="*60)
            print("📌 Step 2: 같은 시간대 내 소모 (cost=10)")
            print("="*60)
            
            resp = await client.post("/api/v1/stats/hp/spend", json={"cost": 10})
            data = resp.json()
            print(f"  결과: HP={data['hp']}, period={data['current_period']}, transition={data['transition'] is not None}")
            
            check("HP 90으로 감소", data["hp"] == 90)
            check("morning 유지", data["current_period"] == "morning")
            check("전환 없음", data["transition"] is None)

            # ══════════════════════════════════════════════
            # Step 3: plusHp 부여 후 우선 소모
            # ══════════════════════════════════════════════
            print("\n" + "="*60)
            print("📌 Step 3: plusHp 우선 소모 테스트")
            print("="*60)
            
            # plusHp 20 부여
            await client.post("/api/v1/stats", json={"updates": {"plusHp": 20}})
            print("  plusHp=20 부여 완료")
            
            # cost=25 → plusHp 20 소모 + baseHp 5 소모
            resp = await client.post("/api/v1/stats/hp/spend", json={"cost": 25})
            data = resp.json()
            print(f"  cost=25 소모 결과: HP={data['hp']}, plusHp={data['plus_hp']}")
            
            check("plusHp 0으로 소진", data["plus_hp"] == 0)
            check("base HP 85 (90-5)", data["hp"] == 85)
            check("morning 유지 (85 >= 76)", data["current_period"] == "morning")

            # ══════════════════════════════════════════════
            # Step 4: 시간대 경계 돌파 (morning → afternoon)
            # ══════════════════════════════════════════════
            print("\n" + "="*60)
            print("📌 Step 4: morning → afternoon 전환 (cost=15)")
            print("="*60)
            
            # HP 85 - 15 = 70 → afternoon (76 미만)
            # 페널티 5 (방 미지정) → 65
            resp = await client.post("/api/v1/stats/hp/spend", json={"cost": 15})
            data = resp.json()
            trans = data.get("transition")
            print(f"  결과: HP={data['hp']}, period={data['current_period']}")
            if trans:
                print(f"  전환: {trans['message']}")
                print(f"  페널티: {trans.get('penalty')}")
            
            check("전환 발생", trans is not None)
            check("afternoon으로 전환", data["current_period"] == "afternoon")
            check("HP 65 (70-5 페널티)", data["hp"] == 65)
            check("페널티 5", trans and trans["penalty"]["amount"] == 5)

            # ══════════════════════════════════════════════
            # Step 5: 휴식 가능 방에서 전환 (페널티 없음)
            # ══════════════════════════════════════════════
            print("\n" + "="*60)
            print("📌 Step 5: afternoon → evening (휴식 가능 방, 페널티 없음)")
            print("="*60)
            
            # HP 65 - 20 = 45 → evening (51 미만)
            # room003은 REST_ROOMS → 페널티 0
            resp = await client.post("/api/v1/stats/hp/spend", json={"cost": 20, "room_id": "room003"})
            data = resp.json()
            trans = data.get("transition")
            print(f"  결과: HP={data['hp']}, period={data['current_period']}")
            
            check("evening으로 전환", data["current_period"] == "evening")
            check("HP 45 (페널티 없음)", data["hp"] == 45)
            check("페널티 없음", trans and trans["penalty"] is None)

            # ══════════════════════════════════════════════
            # Step 6: evening → night 전환
            # ══════════════════════════════════════════════
            print("\n" + "="*60)
            print("📌 Step 6: evening → night (cost=25)")
            print("="*60)
            
            # HP 45 - 25 = 20 → night (26 미만)
            # 페널티 5 → 15
            resp = await client.post("/api/v1/stats/hp/spend", json={"cost": 25})
            data = resp.json()
            print(f"  결과: HP={data['hp']}, period={data['current_period']}")
            
            check("night으로 전환", data["current_period"] == "night")
            check("HP 15 (20-5)", data["hp"] == 15)

            # ══════════════════════════════════════════════
            # Step 7: HP 고갈 → 다음 날 전환
            # ══════════════════════════════════════════════
            print("\n" + "="*60)
            print("📌 Step 7: HP 고갈 → Day 2 전환")
            print("="*60)
            
            # HP 15 전부 소모
            resp = await client.post("/api/v1/stats/hp/spend", json={"cost": 15})
            data = resp.json()
            trans = data.get("transition")
            print(f"  결과: HP={data['hp']}, period={data['current_period']}, day={data['current_day']}")
            if trans:
                print(f"  전환: {trans['message']}")
            
            check("Day 2로 전환", data["current_day"] == 2)
            check("morning으로 리셋", data["current_period"] == "morning")
            check("HP 95 (100-5 페널티)", data["hp"] == 95)
            check("전환 발생", trans is not None)
            check("다음 날 정보", trans and trans["next_day"] == 2)

            # ══════════════════════════════════════════════
            # Step 8: 체력 부족 시 실패
            # ══════════════════════════════════════════════
            print("\n" + "="*60)
            print("📌 Step 8: 체력 부족 시 실패 (cost=200)")
            print("="*60)
            
            resp = await client.post("/api/v1/stats/hp/spend", json={"cost": 200})
            data = resp.json()
            print(f"  결과: success={data['success']}, HP={data['hp']}")
            
            check("실패 반환", data["success"] is False)
            check("HP 변동 없음", data["hp"] == 95)

            # ══════════════════════════════════════════════
            # Step 9: 프리뷰 API 검증
            # ══════════════════════════════════════════════
            print("\n" + "="*60)
            print("📌 Step 9: HP 프리뷰 API")
            print("="*60)
            
            # 같은 기간 내 소모 프리뷰
            resp = await client.post("/api/v1/stats/hp/preview", json={"cost": 5})
            preview = resp.json()
            print(f"  cost=5 프리뷰: affordable={preview['affordable']}, transition={preview['will_transition']}")
            check("소모 가능", preview["affordable"])
            check("전환 없음", preview["will_transition"] is False)
            
            # 전환 발생할 소모 프리뷰
            resp = await client.post("/api/v1/stats/hp/preview", json={"cost": 30})
            preview = resp.json()
            print(f"  cost=30 프리뷰: affordable={preview['affordable']}, transition={preview['will_transition']}, to={preview['to_period']}")
            check("전환 발생 예측", preview["will_transition"])
            check("afternoon으로 전환 예측", preview["to_period"] == "afternoon")
            
            # 감당 못하는 소모 프리뷰
            resp = await client.post("/api/v1/stats/hp/preview", json={"cost": 999})
            preview = resp.json()
            check("감당 불가 판정", preview["affordable"] is False)

            # ══════════════════════════════════════════════
            # Step 10: hp_events DB 히스토리 검증
            # ══════════════════════════════════════════════
            print("\n" + "="*60)
            print("📌 Step 10: hp_events DB 히스토리 검증")
            print("="*60)
            
            cursor = db["hp_events"].find(
                {"user_id": test_user_id},
                {"_id": 0}
            ).sort("timestamp", 1)
            events = await cursor.to_list(length=100)
            
            print(f"  총 HP 이벤트: {len(events)}건")
            check("6건의 HP 이벤트 기록", len(events) == 6)
            
            for i, ev in enumerate(events):
                b = ev["before"]
                a = ev["after"]
                trans_mark = "⚡" if ev["transition_triggered"] else "  "
                print(f"    {trans_mark} [{i+1}] cost={ev['cost']:>3} | "
                      f"HP {b['hp']:>3}→{a['hp']:>3} | "
                      f"plusHp {b['plusHp']:>2}→{a['plusHp']:>2} | "
                      f"{b['period']:>9}→{a['period']:<9} | "
                      f"Day {b['day']}→{a['day']}")
            
            # 이벤트 순서 검증
            if len(events) >= 6:
                check("이벤트1: 일반 소모 (100→90)", events[0]["cost"] == 10 and events[0]["after"]["hp"] == 90)
                check("이벤트2: plusHp 소모 (90→85)", events[1]["cost"] == 25 and events[1]["after"]["hp"] == 85)
                check("이벤트3: morning→afternoon", events[2]["transition_triggered"] and events[2]["after"]["period"] == "afternoon")
                check("이벤트4: afternoon→evening", events[3]["transition_triggered"] and events[3]["after"]["period"] == "evening")
                check("이벤트5: evening→night", events[4]["transition_triggered"] and events[4]["after"]["period"] == "night")
                check("이벤트6: HP 고갈→Day 2", events[5]["transition_triggered"] and events[5]["after"]["day"] == 2)
            
            # ══════════════════════════════════════════════
            # 최종 결과
            # ══════════════════════════════════════════════
            print("\n" + "="*60)
            if failed == 0:
                print(f"🎉 모든 테스트 통과! ({passed}/{total_tests})")
            else:
                print(f"⚠️ 테스트 결과: {passed}/{total_tests} 통과, {failed}건 실패")
            print("="*60)
            
        except Exception as e:
            print(f"\n❌ 테스트 실패: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 테스트 데이터 정리
            print("\n🧹 [Cleanup] 테스트 데이터 삭제 중...")
            await db["tokens"].delete_many({"user_id": test_user_id})
            await db["npc"].delete_many({"user_id": test_user_id})
            await db["inventories"].delete_many({"user_id": test_user_id})
            await db["hp_events"].delete_many({"user_id": test_user_id})
            print("✅ [Cleanup] 완료")


if __name__ == "__main__":
    asyncio.run(main())
