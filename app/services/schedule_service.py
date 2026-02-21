import random
from typing import Dict, List, Tuple, Any
from app.services.base_service import BaseService

class ScheduleService(BaseService):
    def __init__(self):
        super().__init__()
        self.schedule_collection = self.db["schedules"]
        self.topics_collection = self.db["npc_topics"]

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

    async def map_npc_locations(self, day: int, session: int) -> Dict[str, List[str]]:
        """특정 일차 및 세션의 NPC 위치(방)를 그룹핑하여 반환합니다."""
        session_key = self.session_map.get(session, "morning")
        day_str = str(day)
        
        room_groups: Dict[str, List[str]] = {}
        
        # MongoDB에서 스케줄 조회
        cursor = self.schedule_collection.find({}, {"_id": 0})
        schedules_list = await cursor.to_list(length=100)
        
        for npc_schedule in schedules_list:
            npc_id = npc_schedule.get("npc_id")
            schedule_data = npc_schedule.get("schedule", {})
            
            # 특정 일차 스케줄 우선, 없으면 default 스케줄 사용
            daily_schedule = schedule_data.get(day_str, schedule_data.get("default", {}))
            room_id = daily_schedule.get(session_key)
            
            if room_id:
                if room_id not in room_groups:
                    room_groups[room_id] = []
                room_groups[room_id].append(npc_id)
                
        return room_groups

    async def assign_group_topics(self, grouped_locations: Dict[str, List[str]]) -> List[Dict[str, Any]]:
        """동일한 방에 배치된 NPC 그룹에 대화 주제를 할당하여 맵 구성 정보를 반환합니다."""
        map_config = []
        
        # MongoDB에서 주제 풀 준비
        topics_pool = []
        cursor = self.topics_collection.find({}, {"_id": 0})
        topics_list = await cursor.to_list(length=100)
        for session_cat in topics_list:
            topics_pool.extend(session_cat.get("topics", []))
            
        for room_id, npcs in grouped_locations.items():
            room_info = {
                "room_id": room_id,
                "npcs": npcs,
                "topic": None
            }
            
            # 같은 방에 2명 이상의 NPC가 있으면 토픽 부여
            if len(npcs) > 1 and topics_pool:
                # 임시로 랜덤한 토픽 할당 (차후 NPC 조합이나 일차 기반으로 고도화 가능)
                topic = random.choice(topics_pool)
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
        config = await self.assign_group_topics(grouped)
        return {
            "day_index": day,
            "session_index": session,
            "session_name": self.session_map.get(session, "unknown"),
            "room_placements": config
        }

schedule_service = ScheduleService()

