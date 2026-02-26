import uuid
import json
import os
from typing import Dict, Optional, Any
from datetime import datetime

from app.services.base_service import BaseService
from app.core.security import create_access_token, verify_token, create_refresh_token


# ── 세션별 HP 배분 ──
SESSION_HP_MAP = {
    "morning": 30,
    "afternoon": 30,
    "evening": 30,
    "night": 10,
}

SESSION_ORDER = ["morning", "afternoon", "evening", "night"]
SESSION_INDEX_MAP = {name: idx + 1 for idx, name in enumerate(SESSION_ORDER)}

SESSION_MESSAGES = {
    "morning": "아침이 밝았다. 새로운 하루가 시작된다.",
    "afternoon": "점심시간이 다 됐군... 식당으로 가볼까.",
    "evening": "해가 기울기 시작한다.",
    "night": "밤이 깊어간다...",
}


class StatsService(BaseService):

    def __init__(self):
        super().__init__()
        # stats는 token 저장소와 분리해서 관리
        self.collection_stats = self.db["user_stats"]
        self.collection_npc = self.db["npc_stats"]
        # 하위 호환: 기존 테스트 코드에서 collection_token 참조하는 경우 대응
        self.collection_token = self.collection_stats

    def _default_stats_doc(self, user_id: str) -> Dict[str, Any]:
        return {
            "user_id": user_id,
            "fishLevel": 0,
            "total_hp": 100,
            "session_hp": 30,
            "plus_hp": 0,
            "current_session": "morning",
            "current_day": 0,
            "floor_id": None,
            "room_id": None,
            "created_at": datetime.now(),
        }

    def _session_to_index(self, session_name: str) -> int:
        return SESSION_INDEX_MAP.get(session_name, 1)

    def _with_session_index(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        enriched = dict(stats)
        enriched["current_session_index"] = self._session_to_index(
            enriched.get("current_session", "morning")
        )
        return enriched

    async def get_current_stats(self, user_id: str):
        # 1) 신규 컬렉션 우선 조회
        stats = await self.collection_stats.find_one({"user_id": user_id})
        if stats:
            return self._with_session_index(stats)

        # 2) 레거시 fallback: tokens에 스탯 문서가 있을 수 있음
        legacy = await self.db["tokens"].find_one({"user_id": user_id, "total_hp": {"$exists": True}})
        if legacy:
            return self._with_session_index(legacy)

        # 3) 로그인 직후 /stats 호출 시 기본 스탯 자동 생성
        default_doc = self._default_stats_doc(user_id)
        await self.collection_stats.update_one(
            {"user_id": user_id},
            {"$setOnInsert": default_doc},
            upsert=True
        )
        created = await self.collection_stats.find_one({"user_id": user_id})
        return self._with_session_index(created)

    async def get_current_NPC_stats(self, user_id: str, npc_id: str):
        stats = await self.collection_npc.find_one({"user_id": user_id, "npcId": npc_id})
        if stats:
            return stats
        # 레거시 fallback
        return await self.db["npc"].find_one({"user_id": user_id, "npcId": npc_id})

    async def update_stats(self, updates: dict, user_id: str):
        filter_query = {"user_id": user_id}
        update_query = {"$set": updates}
        await self.collection_stats.update_one(
            filter_query, update_query, upsert=True
        )
        return await self.get_current_stats(user_id)

    async def update_NPC_stats(self, updates: dict, npc_id: str, user_id: str):
        filter_query = {"user_id": user_id, "npcId": npc_id}
        update_query = {"$set": updates}
        await self.collection_npc.update_one(filter_query, update_query, upsert=True)
        return await self.get_current_NPC_stats(user_id, npc_id)

    async def static_stats(self, user_id: str):
        """유저 스탯 생성 (Day 0 = 튜토리얼)"""
        initial_stats = self._default_stats_doc(user_id)
        await self.collection_stats.update_one(
            {"user_id": user_id},
            {"$set": initial_stats},
            upsert=True
        )

        await self.insert_initial_npc_stats(user_id)

        initial_items = {f"item{i:03d}": (i <= 3) for i in range(1, 100)}
        await self.db["inventories"].insert_one({
            "user_id": user_id,
            "items": initial_items,
            "created_at": datetime.now()
        })

        return {
            "fishLevel": 0,
            "total_hp": 100,
            "session_hp": 30,
            "plus_hp": 0,
            "current_session": "morning",
            "current_session_index": 1,
            "current_day": 0,
        }
        
    async def insert_initial_npc_stats(self, user_id: str):
        file_path = os.path.join(os.path.dirname(__file__), "..", "data", "characters.json")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                npc_data_map = json.load(f)
                npc_documents = []
                for npc_name, char_info in npc_data_map.items():
                    if char_info.get("isHardcoded"):
                        continue
                    npc_stats = char_info.get("initialStats", {})
                    npc_documents.append({
                        "user_id": user_id,
                        "npcId": npc_name,
                        "friendly": npc_stats.get("friendly", 0),
                        "faith": npc_stats.get("faith", 0),
                        "fishLevel": npc_stats.get("fishLevel", 0),
                        "created_at": datetime.now()
                    })
                if npc_documents:
                    await self.collection_npc.insert_many(npc_documents)
        except FileNotFoundError:
            raise FileNotFoundError(f"Character data file not found at: {file_path}")

    # ================================================================
    # HP 관리 로직 (3-Tier: total_hp / session_hp / plus_hp)
    # ================================================================

    def _build_hp_response(self, success: bool, stats: Dict, message: Optional[str] = None) -> Dict:
        """HP 응답 공통 빌더"""
        return {
            "success": success,
            "total_hp": stats.get("total_hp", 0),
            "session_hp": stats.get("session_hp", 0),
            "plus_hp": stats.get("plus_hp", 0),
            "current_session": stats.get("current_session", "morning"),
            "current_session_index": self._session_to_index(stats.get("current_session", "morning")),
            "current_day": stats.get("current_day", 1),
            "floor_id": stats.get("floor_id"),
            "room_id": stats.get("room_id"),
            "message": message,
        }

    async def _log_hp_event(self, user_id: str, cost: int, message: Optional[str],
                            before: Dict, after: Dict):
        """HP 소모 이벤트를 hp_events 컬렉션에 기록"""
        event = {
            "user_id": user_id,
            "cost": cost,
            "message": message,
            "before": {
                "total_hp": before.get("total_hp"),
                "session_hp": before.get("session_hp"),
                "plus_hp": before.get("plus_hp"),
                "session": before.get("current_session"),
                "day": before.get("current_day"),
            },
            "after": {
                "total_hp": after.get("total_hp"),
                "session_hp": after.get("session_hp"),
                "plus_hp": after.get("plus_hp"),
                "session": after.get("current_session"),
                "day": after.get("current_day"),
            },
            "timestamp": datetime.now(),
        }
        await self.db["hp_events"].insert_one(event)

    async def spend_hp(self, user_id: str, cost: int, message: Optional[str] = None, floor_id: Optional[str] = None, room_id: Optional[str] = None) -> Dict[str, Any]:
        """
        HP를 소모합니다.
        1. plus_hp 우선 소모
        2. 부족하면 session_hp에서 소모
        3. available > 0이면 부족해도 1회 허용 (다음 세션에서 차감)
        4. available <= 0이면 거부 (이미 다 쓴)
        5. total_hp도 동시에 감소
        6. floor_id와 room_id가 전달되면 위치 정보 업데이트
        """
        stats = await self.get_current_stats(user_id)
        if not stats:
            return {"success": False, "total_hp": 0, "session_hp": 0, "plus_hp": 0,
                    "current_session": "morning", "current_day": 1,
                    "session_depleted": True, "message": "유저 정보를 찾을 수 없습니다."}

        total_hp = stats.get("total_hp", 100)
        session_hp = stats.get("session_hp", 30)
        plus_hp = stats.get("plus_hp", 0)
        available = session_hp + plus_hp

        # 이미 소진됨 (땅겨쓰기 후 또는 정확히 다 쓴)
        if available <= 0:
            resp = self._build_hp_response(False, stats, "HP가 소진되었습니다. 다음 세션으로 전환해주세요.")
            resp["session_depleted"] = True
            return resp

        before_state = dict(stats)

        # plus_hp 우선 소모
        remaining = cost
        new_plus = plus_hp
        if new_plus > 0:
            from_plus = min(remaining, new_plus)
            new_plus -= from_plus
            remaining -= from_plus

        # 나머지를 session_hp에서 차감 (마이너스 가능 = 다음 세션에서 땅겨쓰기)
        new_session = session_hp - remaining
        new_total = total_hp - cost

        stats_update = {
            "total_hp": new_total,
            "session_hp": new_session,
            "plus_hp": new_plus,
        }
        
        if floor_id is not None:
            stats_update["floor_id"] = floor_id
        if room_id is not None:
            stats_update["room_id"] = room_id

        await self.update_stats(stats_update, user_id)

        after_stats = await self.get_current_stats(user_id)
        await self._log_hp_event(user_id, cost, message, before_state, after_stats)

        # 세션 소진 판단: 소모 후 남은 available <= 0
        new_available = new_session + new_plus
        resp = self._build_hp_response(True, after_stats, message)
        resp["session_depleted"] = (new_available <= 0)
        return resp

    async def advance_session(self, user_id: str) -> Dict[str, Any]:
        """
        다음 세션으로 전환합니다.
        - session_hp >= 0: 남은 session_hp를 plus_hp로 이월
        - session_hp < 0: 땅겨쓴 부채 → 다음 세션 HP에서 차감
        - night → morning: day++, total_hp = 100 + 이월분
        """
        stats = await self.get_current_stats(user_id)
        if not stats:
            return {"success": False, "previous_session": "", "current_session": "",
                    "previous_session_index": 0, "current_session_index": 0,
                    "total_hp": 0, "session_hp": 0, "plus_hp": 0,
                    "current_day": 1, "message": "유저 정보를 찾을 수 없습니다."}

        current_session = stats.get("current_session", "morning")
        current_day = stats.get("current_day", 1)
        session_hp = stats.get("session_hp", 0)

        idx = SESSION_ORDER.index(current_session)

        if current_session == "night":
            next_session = "morning"
            next_day = current_day + 1
        else:
            next_session = SESSION_ORDER[idx + 1]
            next_day = current_day

        base_session_hp = SESSION_HP_MAP[next_session]

        if session_hp < 0:
            # 땅겨쓴 부채: 다음 세션 HP에서 차감
            new_session_hp = base_session_hp + session_hp  # e.g. 30 + (-7) = 23
            new_plus = 0
        else:
            # 남은 HP 이월
            new_session_hp = base_session_hp
            new_plus = session_hp

        # Day 0(튜토리얼) -> Day 1 전환 시 HP는 반드시 초기화
        if current_day == 0 and next_day == 1 and next_session == "morning":
            new_total = 100
            new_session_hp = SESSION_HP_MAP["morning"]
            new_plus = 0
            msg = "튜토리얼이 종료되었습니다. Day 1이 시작됩니다."
        elif current_session == "night":
            new_total = 100 + max(0, session_hp)  # 이월분만 더함, 부채는 session_hp에 이미 반영
            msg = f"Day {next_day} — {SESSION_MESSAGES['morning']}"
        else:
            new_total = stats.get("total_hp", 100)
            msg = SESSION_MESSAGES.get(next_session, "")

        await self.update_stats({
            "current_session": next_session,
            "current_day": next_day,
            "total_hp": new_total,
            "session_hp": new_session_hp,
            "plus_hp": new_plus,
        }, user_id)

        return {
            "success": True,
            "previous_session": current_session,
            "current_session": next_session,
            "previous_session_index": self._session_to_index(current_session),
            "current_session_index": self._session_to_index(next_session),
            "total_hp": new_total,
            "session_hp": new_session_hp,
            "plus_hp": new_plus,
            "current_day": next_day,
            "message": msg,
        }


stats_service = StatsService()
