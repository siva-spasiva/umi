import os
import json
import hashlib
from typing import Dict, List, Tuple, Any
from app.services.base_service import BaseService

class ScheduleService(BaseService):
    def __init__(self):
        super().__init__()
        self.schedule_collection = self.db["schedules"]
        self.topics_collection = self.db["npc_topics"]
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.schedule_json_path = os.path.join(self.base_dir, "data", "schedule.json")
        self.topics_json_path = os.path.join(self.base_dir, "data", "NPC_topics.json")

        # 세션 인덱스를 문자열 키로 매핑
        self.session_map = {
            1: "morning",
            2: "afternoon",
            3: "evening",
            4: "night"
        }

    def get_next_session_info(self, current_day: int, current_session: int) -> Tuple[int, int]:
        """현재 세션을 기준으로 다음 세션의 인덱스와 일차를 계산합니다."""
        if current_session >= 4:
            return current_day + 1, 1
        return current_day, current_session + 1

    def _normalize_room_id(self, room_id: Any) -> str:
        """
        스케줄 room_id를 정규화합니다.
        - None, 빈 문자열, "null"/"none" 문자열은 빈 값으로 간주
        - room id는 대소문자 불일치를 피하기 위해 소문자로 통일
        """
        if room_id is None:
            return ""
        if isinstance(room_id, str):
            normalized = room_id.strip()
            if not normalized:
                return ""
            if normalized.lower() in {"null", "none"}:
                return ""
            return normalized.lower()
        return str(room_id).strip().lower()

    def _normalize_npc_id(self, npc_id: Any) -> str:
        if npc_id is None:
            return ""
        key = str(npc_id).strip().lower()
        return key

    async def _get_schedule_documents(self) -> List[Dict[str, Any]]:
        """
        스케줄 문서를 우선 DB에서 조회하고, 비어 있으면 로컬 JSON을 fallback으로 사용합니다.
        반환 형식: [{"npc_id": "...", "schedule": {...}}, ...]
        """
        cursor = self.schedule_collection.find({}, {"_id": 0})
        schedules_list = await cursor.to_list(length=500)
        if schedules_list:
            return schedules_list

        if not os.path.exists(self.schedule_json_path):
            return []

        try:
            with open(self.schedule_json_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            docs: List[Dict[str, Any]] = []
            for npc_id, schedule_info in raw_data.items():
                docs.append({
                    "npc_id": self._normalize_npc_id(npc_id),
                    "schedule": schedule_info or {}
                })
            return docs
        except Exception:
            return []

    async def _get_topics_pool(self) -> List[Dict[str, Any]]:
        """
        토픽 풀을 우선 DB에서 조회하고, 비어 있으면 로컬 JSON을 fallback으로 사용합니다.
        """
        cursor = self.topics_collection.find({}, {"_id": 0})
        topics_list = await cursor.to_list(length=200)
        pool: List[Dict[str, Any]] = []
        for session_cat in topics_list:
            pool.extend(session_cat.get("topics", []))

        if pool:
            return pool

        if not os.path.exists(self.topics_json_path):
            return []

        try:
            with open(self.topics_json_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            for session_cat in raw_data.get("npc_dialogue_sessions", []):
                pool.extend(session_cat.get("topics", []))
            return pool
        except Exception:
            return []

    async def map_npc_locations(self, day: int, session: int) -> Dict[str, List[str]]:
        """특정 일차 및 세션의 NPC 위치(방)를 그룹핑하여 반환합니다."""
        session_key = self.session_map.get(session, "morning")
        day_str = str(day)
        
        room_groups: Dict[str, List[str]] = {}
        
        schedules_list = await self._get_schedule_documents()
        
        for npc_schedule in schedules_list:
            npc_id = self._normalize_npc_id(npc_schedule.get("npc_id"))
            schedule_data = npc_schedule.get("schedule", {})
            
            # 특정 일차 스케줄 우선, 없으면 default 스케줄 사용
            daily_schedule = schedule_data.get(day_str, schedule_data.get("default", {}))
            room_id = self._normalize_room_id(daily_schedule.get(session_key))

            if room_id and npc_id:
                if room_id not in room_groups:
                    room_groups[room_id] = []
                room_groups[room_id].append(npc_id)
                
        return room_groups

    async def assign_group_topics(self, grouped_locations: Dict[str, List[str]], day: int, session: int) -> List[Dict[str, Any]]:
        """동일한 방에 배치된 NPC 그룹에 대화 주제를 할당하여 맵 구성 정보를 반환합니다."""
        map_config = []
        topics_pool = await self._get_topics_pool()
            
        for room_id, npcs in grouped_locations.items():
            room_info = {
                "room_id": room_id,
                "npcs": npcs,
                "topic": None
            }
            
            # 같은 방에 2명 이상의 NPC가 있으면 토픽 부여
            if len(npcs) > 1 and topics_pool:
                # 동일 day/session/room에서는 항상 동일 토픽이 배정되도록 결정적 선택
                key = f"{day}:{session}:{room_id}"
                idx = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % len(topics_pool)
                topic = topics_pool[idx]
                room_info["topic"] = {
                    "id": topic.get("id"),
                    "title": topic.get("title"),
                    "context": topic.get("context"),
                    "summary": topic.get("summary")
                }
                
            map_config.append(room_info)
            
        return map_config

    async def generate_map_config(self, day: int, session: int) -> Dict[str, Any]:
        """day, session 정보로 해당 회차의 전체 맵 구성(NPC 배치+토픽) 정보를 리턴합니다."""
        grouped = await self.map_npc_locations(day, session)
        config = await self.assign_group_topics(grouped, day, session)
        return {
            "day_index": day,
            "session_index": session,
            "session_name": self.session_map.get(session, "unknown"),
            "room_placements": config
        }

    async def get_full_timeline(self, day_start: int = 0, day_end: int = 5) -> Dict[str, Any]:
        """
        전체 일정 확인용:
        - raw 스케줄 문서
        - day/session별 계산된 맵 배치 결과
        """
        if day_start > day_end:
            day_start, day_end = day_end, day_start

        schedules = await self._get_schedule_documents()
        timeline: List[Dict[str, Any]] = []
        for day in range(day_start, day_end + 1):
            for session in (1, 2, 3, 4):
                timeline.append(await self.generate_map_config(day, session))

        return {
            "day_range": {"start": day_start, "end": day_end},
            "schedule_count": len(schedules),
            "schedules": schedules,
            "timeline": timeline
        }

schedule_service = ScheduleService()
