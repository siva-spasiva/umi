import uuid
import json
import os
from typing import Dict, Optional, Any
from datetime import datetime

from app.services.base_service import BaseService
from app.core.security import create_access_token, verify_token, create_refresh_token


# ── HP ↔ 시간대 매핑 (프론트엔드 로직 그대로 서버로 이식) ──
HP_PERIOD_THRESHOLDS = [
    (76, "morning"),    # 76~100
    (51, "afternoon"),  # 51~75
    (26, "evening"),    # 26~50
    (1,  "night"),      # 1~25
]

SECTION_TRANSITIONS = {
    "morning": {
        "next": "afternoon",
        "message": "점심시간이 다 됐군... 식당으로 가볼까.",
        "target_room": "cafeteria",
    },
    "afternoon": {
        "next": "evening",
        "message": "해가 기울기 시작한다. 저녁 준비를 해야겠어.",
        "target_room": None,
    },
    "evening": {
        "next": "night",
        "message": "밤이 깊어간다... 오늘은 여기까지.",
        "target_room": None,
    },
    "night": {
        "next": "dawn",
        "message": "새벽이 밝아온다...",
        "target_room": None,
    },
    "dawn": {
        "next": "morning",
        "message": "새로운 하루가 시작된다.",
        "target_room": "room001",
    },
}

# 휴식 가능한 방 목록
REST_ROOMS = {"room001", "room002", "room003", "room004", "room005"}


def get_period_from_hp(hp: int) -> Optional[str]:
    """base HP 값에 따른 시간대를 반환"""
    for threshold, period in HP_PERIOD_THRESHOLDS:
        if hp >= threshold:
            return period
    return None


class StatsService(BaseService):

    def __init__(self):
        super().__init__()
        self.collection_token = self.db["tokens"]
        self.collection_npc = self.db["npc"]

    async def get_current_stats(self, user_id: str):
        stats = await self.collection_token.find_one({"user_id": user_id})
        return stats

    async def get_current_NPC_stats(self, user_id: str, npc_id: str):
        stats = await self.collection_npc.find_one({"user_id": user_id, "npcId": npc_id})
        return stats

    async def update_stats(self, updates: dict, user_id: str):
        filter_query = {"user_id": user_id}
        update_query = {"$set": updates}
        await self.collection_token.update_one(
            filter_query,
            update_query,
            upsert=True
        )
        return await self.get_current_stats(user_id)

    async def update_NPC_stats(self, updates: dict, npc_id: str, user_id: str):
        filter_query = {"user_id": user_id, "npcId": npc_id}
        update_query = {"$set": updates}
        await self.collection_npc.update_one(filter_query, update_query, upsert=True)
        return await self.get_current_NPC_stats(user_id, npc_id)

    async def static_stats(self, user_id: str):
        """유저 스탯 생성"""
        initial_stats = {
            "user_id": user_id,
            "fishLevel": 0,
            "hp": 100,
            "plusHp": 0,
            "currentPeriod": "morning",
            "currentDay": 1,
            "friendly": 50,
            "trust": 0,
            "created_at": datetime.now()
        }
        await self.collection_token.insert_one(initial_stats)

        # NPC stats 생성
        await self.insert_initial_npc_stats(user_id)

        # 초기 인벤토리 생성
        initial_items = {f"{i:03d}": (i <= 3) for i in range(1, 100)}
        await self.db["inventories"].insert_one({
            "user_id": user_id,
            "items": initial_items,
            "created_at": datetime.now()
        })

        return {
            "fishLevel": 0, "hp": 100, "friendly": 50, "trust": 0
        }
        
    async def insert_initial_npc_stats(self, user_id: str):
        file_path = os.path.join(os.path.dirname(__file__), "..", "data", "characters.json")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                npc_data_map = json.load(f)
                npc_documents = []
                for npc_name, char_info in npc_data_map.items():
                    # isHardcoded NPC는 스탯이 없으므로 건너뛰기
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
    # HP 관리 로직
    # ================================================================

    async def _log_hp_event(self, user_id: str, cost: int, room_id: Optional[str],
                            before: Dict, after: Dict, transition: Optional[Dict]):
        """HP 소모 이벤트를 hp_events 컬렉션에 기록"""
        event = {
            "user_id": user_id,
            "cost": cost,
            "room_id": room_id,
            "before": {
                "hp": before["hp"],
                "plusHp": before["plusHp"],
                "period": before["period"],
                "day": before["day"],
            },
            "after": {
                "hp": after["hp"],
                "plusHp": after["plusHp"],
                "period": after["period"],
                "day": after["day"],
            },
            "transition_triggered": transition is not None,
            "transition": transition,
            "timestamp": datetime.now(),
        }
        await self.db["hp_events"].insert_one(event)

    async def spend_hp(self, user_id: str, cost: int, room_id: Optional[str] = None) -> Dict[str, Any]:
        """
        HP를 소모합니다. plusHp 우선 소모 후 base HP에서 차감.
        시간대 경계를 넘으면 섹션 전환 정보를 반환합니다.
        소모 이력은 hp_events 컬렉션에 자동 기록됩니다.
        
        Returns:
            {success, hp, plus_hp, current_period, current_day, transition}
        """
        stats = await self.get_current_stats(user_id)
        if not stats:
            return {"success": False, "hp": 0, "plus_hp": 0, "current_period": "morning", "current_day": 1, "transition": None}
        
        base_hp = stats.get("hp", 100)
        current_plus = stats.get("plusHp", 0)
        current_period = stats.get("currentPeriod", "morning")
        current_day = stats.get("currentDay", 1)
        total_hp = base_hp + current_plus

        before_state = {"hp": base_hp, "plusHp": current_plus, "period": current_period, "day": current_day}

        # 체력 부족
        if total_hp < cost:
            return {"success": False, "hp": base_hp, "plus_hp": current_plus, 
                    "current_period": current_period, "current_day": current_day, "transition": None}

        # plusHp 우선 소모
        remaining_cost = cost
        new_plus = current_plus
        if new_plus > 0:
            from_plus = min(remaining_cost, new_plus)
            new_plus -= from_plus
            remaining_cost -= from_plus

        # 나머지를 base HP에서 차감
        new_hp = base_hp - remaining_cost
        new_period = get_period_from_hp(new_hp)

        has_rest = room_id in REST_ROOMS if room_id else False
        transition = None

        if new_hp <= 0:
            # base HP 소진 → 다음 날로 진행
            next_day = min(current_day + 1, 7)
            penalty = 0 if has_rest else 5
            hp_after = 100 - penalty

            transition = {
                "message": SECTION_TRANSITIONS["dawn"]["message"],
                "target_room": SECTION_TRANSITIONS["dawn"]["target_room"],
                "next_period": "morning",
                "next_day": next_day,
                "hp_after": hp_after,
                "plus_hp_after": 0,
                "penalty": {"amount": penalty, "message": "피곤하다..."} if penalty > 0 else None,
            }

            await self.update_stats({
                "hp": hp_after, "plusHp": 0,
                "currentPeriod": "morning", "currentDay": next_day,
            }, user_id)

            after_state = {"hp": hp_after, "plusHp": 0, "period": "morning", "day": next_day}
            await self._log_hp_event(user_id, cost, room_id, before_state, after_state, transition)

            return {"success": True, "hp": hp_after, "plus_hp": 0,
                    "current_period": "morning", "current_day": next_day, "transition": transition}

        if new_period and new_period != current_period:
            # 시간대 경계 돌파 → 섹션 전환
            penalty = 0 if has_rest else 5
            hp_after_penalty = max(0, new_hp - penalty)

            trans_info = SECTION_TRANSITIONS.get(current_period)
            if trans_info:
                transition = {
                    "message": trans_info["message"],
                    "target_room": trans_info["target_room"],
                    "next_period": trans_info["next"],
                    "next_day": None,
                    "hp_after": hp_after_penalty,
                    "plus_hp_after": 0,
                    "penalty": {"amount": penalty, "message": "피곤하다..."} if penalty > 0 else None,
                }

            await self.update_stats({
                "hp": hp_after_penalty, "plusHp": 0,
                "currentPeriod": new_period,
            }, user_id)

            after_state = {"hp": hp_after_penalty, "plusHp": 0, "period": new_period, "day": current_day}
            await self._log_hp_event(user_id, cost, room_id, before_state, after_state, transition)

            return {"success": True, "hp": hp_after_penalty, "plus_hp": 0,
                    "current_period": new_period, "current_day": current_day, "transition": transition}
        else:
            # 같은 시간대 내 소모
            await self.update_stats({
                "hp": new_hp, "plusHp": new_plus,
            }, user_id)

            after_state = {"hp": new_hp, "plusHp": new_plus, "period": current_period, "day": current_day}
            await self._log_hp_event(user_id, cost, room_id, before_state, after_state, None)

            return {"success": True, "hp": new_hp, "plus_hp": new_plus,
                    "current_period": current_period, "current_day": current_day, "transition": None}

    async def get_hp_cost_preview(self, user_id: str, cost: int) -> Dict[str, Any]:
        """
        HP 소모 시 어떤 변화가 일어나는지 미리 보기 (DB 변경 없음)
        """
        stats = await self.get_current_stats(user_id)
        if not stats:
            return {"affordable": False, "will_transition": False}
        
        base_hp = stats.get("hp", 100)
        current_plus = stats.get("plusHp", 0)
        current_period = stats.get("currentPeriod", "morning")
        total_hp = base_hp + current_plus

        if total_hp < cost:
            return {"affordable": False, "will_transition": False,
                    "from_period": current_period, "to_period": None, "new_hp": None}

        remaining_cost = cost
        tmp_plus = current_plus
        if tmp_plus > 0:
            from_plus = min(remaining_cost, tmp_plus)
            tmp_plus -= from_plus
            remaining_cost -= from_plus

        new_hp = base_hp - remaining_cost
        new_period = get_period_from_hp(new_hp) if new_hp > 0 else None

        will_transition = new_hp <= 0 or (new_period is not None and new_period != current_period)

        return {
            "affordable": True,
            "will_transition": will_transition,
            "from_period": current_period,
            "to_period": "morning" if new_hp <= 0 else new_period,
            "new_hp": new_hp,
        }


stats_service = StatsService()
