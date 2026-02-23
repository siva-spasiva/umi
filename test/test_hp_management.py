"""
=============================================================
3-Tier HP System Test (with Borrow/Debt)
=============================================================

시나리오:
1. 초기화: total=100, session=30(morning), plus=0
2. 일반 소모 (10) → session 20
3. HP 27 소모 (session 20+plus 0=20, cost 27 > 20) → 땡겨쓰기 → session -7
4. 땡겨쓴 후 추가 행동 → 거부 (session_depleted)
5. Session 전환 → debt 적용 (afternoon session = 30-7 = 23)
6. 정상 소모 후 전환 → evening
7. Evening 전부 안쓰고 전환 → Night (plus=30)
8. Night 전부 안쓰고 전환 → Day 2 Morning (plus=10, total=110)
9. hp_events 히스토리
"""

import sys, os, asyncio, uuid
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from app.main import app
from app.core.security import get_current_user_id
from app.core.database import db

test_user_id = f"hp3_test_{uuid.uuid4().hex[:8]}"
app.dependency_overrides[get_current_user_id] = lambda: test_user_id


async def main():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        passed = failed = total = 0

        def check(name, cond, detail=""):
            nonlocal passed, failed, total
            total += 1
            if cond:
                passed += 1; print(f"  ✅ {name}")
            else:
                failed += 1; print(f"  ❌ {name} → {detail}")

        try:
            # ── 1. 초기화 ──
            print("\n" + "="*60)
            print("📌 1. 유저 초기화 (Day 0 = 튜토리얼)")
            print("="*60)
            await c.post("/api/v1/users/login")
            init = (await c.get("/api/v1/stats/static")).json()
            print(f"  유저: {test_user_id}")
            print(f"  초기: day={init['current_day']}, session={init['current_session']}, total={init['total_hp']}")
            check("Day 0 (튜토리얼)", init["current_day"] == 0)
            check("morning 시작", init["current_session"] == "morning")

            # GET /stats로 day/session 조회 확인
            stats = (await c.get("/api/v1/stats")).json()
            check("GET /stats current_day=0", stats["current_day"] == 0)
            check("GET /stats current_session=morning", stats["current_session"] == "morning")
            check("GET /stats total_hp=100", stats["total_hp"] == 100)

            # ── 2. 일반 소모 (10) ──
            print("\n" + "="*60)
            print("📌 2. HP 10 소모")
            print("="*60)
            r = (await c.post("/api/v1/stats/hp/spend", json={"hp": 10, "message": "대화"})).json()
            print(f"  total={r['total_hp']}, session={r['session_hp']}, plus={r['plus_hp']}, depleted={r['session_depleted']}")
            check("total 90", r["total_hp"] == 90)
            check("session 20", r["session_hp"] == 20)
            check("depleted=False", r["session_depleted"] is False)

            # ── 3. 땡겨쓰기 (cost 27 > available 20) ──
            print("\n" + "="*60)
            print("📌 3. 땡겨쓰기 (cost=27, available=20)")
            print("="*60)
            r = (await c.post("/api/v1/stats/hp/spend", json={"hp": 27, "message": "대형 행동"})).json()
            print(f"  success={r['success']}, total={r['total_hp']}, session={r['session_hp']}, depleted={r['session_depleted']}")
            check("성공 (땡겨쓰기 허용)", r["success"] is True)
            check("session -7", r["session_hp"] == -7)
            check("total 63", r["total_hp"] == 63)
            check("session_depleted=True", r["session_depleted"] is True)

            # ── 4. 추가 행동 → 거부 ──
            print("\n" + "="*60)
            print("📌 4. 소진 후 추가 행동 → 거부")
            print("="*60)
            r = (await c.post("/api/v1/stats/hp/spend", json={"hp": 5})).json()
            print(f"  success={r['success']}, msg={r['message']}")
            check("실패", r["success"] is False)
            check("session_depleted=True", r["session_depleted"] is True)

            # ── 5. Morning → Afternoon (debt 적용) ──
            print("\n" + "="*60)
            print("📌 5. Morning → Afternoon (session -7 부채 적용)")
            print("="*60)
            r = (await c.post("/api/v1/stats/hp/advance")).json()
            print(f"  {r['previous_session']} → {r['current_session']}")
            print(f"  total={r['total_hp']}, session={r['session_hp']}, plus={r['plus_hp']}")
            check("afternoon 전환", r["current_session"] == "afternoon")
            check("session 23 (30-7 부채)", r["session_hp"] == 23)
            check("plus 0 (부채라 이월 없음)", r["plus_hp"] == 0)

            # ── 6. Afternoon 5 소모 후 전환 ──
            print("\n" + "="*60)
            print("📌 6. Afternoon HP 5 소모")
            print("="*60)
            r = (await c.post("/api/v1/stats/hp/spend", json={"hp": 5, "message": "탐색"})).json()
            print(f"  total={r['total_hp']}, session={r['session_hp']}, plus={r['plus_hp']}")
            check("session 18", r["session_hp"] == 18)
            check("depleted=False", r["session_depleted"] is False)

            # ── 7. Afternoon → Evening (18 이월) ──
            print("\n" + "="*60)
            print("📌 7. Afternoon → Evening (18 이월)")
            print("="*60)
            r = (await c.post("/api/v1/stats/hp/advance")).json()
            print(f"  total={r['total_hp']}, session={r['session_hp']}, plus={r['plus_hp']}")
            check("session 30", r["session_hp"] == 30)
            check("plus 18", r["plus_hp"] == 18)

            # ── 8. Evening → Night (미소모, 30 이월) ──
            print("\n" + "="*60)
            print("📌 8. Evening → Night (미소모)")
            print("="*60)
            r = (await c.post("/api/v1/stats/hp/advance")).json()
            print(f"  total={r['total_hp']}, session={r['session_hp']}, plus={r['plus_hp']}")
            check("session 10", r["session_hp"] == 10)
            check("plus 30 (evening 전체 이월)", r["plus_hp"] == 30)

            # ── 9. Night → Day 1 Morning (미소모, 10 이월) ──
            print("\n" + "="*60)
            print("📌 9. Night → Day 1 Morning")
            print("="*60)
            r = (await c.post("/api/v1/stats/hp/advance")).json()
            print(f"  Day {r['current_day']}: total={r['total_hp']}, session={r['session_hp']}, plus={r['plus_hp']}")
            check("Day 1", r["current_day"] == 1)
            check("total 110 (100+10)", r["total_hp"] == 110)
            check("session 30", r["session_hp"] == 30)
            check("plus 10", r["plus_hp"] == 10)

            # ── 10. hp_events ──
            print("\n" + "="*60)
            print("📌 10. hp_events DB 히스토리")
            print("="*60)
            cursor = db["hp_events"].find({"user_id": test_user_id}, {"_id": 0}).sort("timestamp", 1)
            events = await cursor.to_list(length=100)
            print(f"  총 이벤트: {len(events)}건")
            check("3건 기록", len(events) == 3)
            for i, ev in enumerate(events):
                b, a = ev["before"], ev["after"]
                print(f"    [{i+1}] cost={ev['cost']:>2} | "
                      f"session {b['session_hp']:>3}→{a['session_hp']:>3} | "
                      f"plus {b['plus_hp']:>2}→{a['plus_hp']:>2} | "
                      f"msg={ev.get('message', '-')}")
            if len(events) >= 3:
                check("이벤트2: 땡겨쓰기 (20→-7)", events[1]["after"]["session_hp"] == -7)
                check("이벤트2 msg: 대형 행동", events[1]["message"] == "대형 행동")

            # ── 결과 ──
            print("\n" + "="*60)
            if failed == 0:
                print(f"🎉 모든 테스트 통과! ({passed}/{total})")
            else:
                print(f"⚠️ 테스트 결과: {passed}/{total} 통과, {failed}건 실패")
            print("="*60)

        except Exception as e:
            print(f"\n❌ 테스트 실패: {e}")
            import traceback; traceback.print_exc()
        finally:
            print("\n🧹 [Cleanup] 테스트 데이터 삭제 중...")
            for col in ["tokens", "npc", "inventories", "hp_events"]:
                await db[col].delete_many({"user_id": test_user_id})
            print("✅ [Cleanup] 완료")


if __name__ == "__main__":
    asyncio.run(main())
