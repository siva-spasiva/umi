"""
NPC 대화(Conversation) 서비스
- NPC-only: NPC끼리 주제를 가지고 자동 대화
- User+NPC: 유저와 NPC들이 함께 주제를 가지고 대화
"""

from typing import List, Dict, Any, Optional
from app.agents.llm_engine import llm_engine
from app.schemas.conversation import (
    ConversationTurn,
    ConversationResponse,
)
from langsmith import traceable


class ConversationService:
    """NPC 대화 서비스"""

    def _build_topic_history_entry(self, topic: str) -> Dict[str, str]:
        """주제를 대화 히스토리의 시스템 메시지 형태로 변환"""
        return {
            "speaker": "system",
            "content": f"[대화 주제] {topic}"
        }

    def _build_conversation_history(
        self,
        topic: str,
        previous_turns: List[Dict[str, Any]]
    ) -> List[Dict[str, str]]:
        """
        대화 주제 + 이전 턴들을 LLM에 전달할 히스토리로 구성.
        기존 llm_engine.ask()가 받는 history 형태에 맞춤:
        [{"speaker": "user"|"npc"|"system", "content": "..."}]
        """
        history: List[Dict[str, str]] = []

        # 1) 주제 시스템 메시지
        history.append(self._build_topic_history_entry(topic))

        # 2) 이전 턴들 추가
        if previous_turns:
            for turn in previous_turns:
                history.append({
                    "speaker": turn.get("speaker_id", turn.get("speaker", "unknown")),
                    "content": turn.get("content", "")
                })

        return history

    def __init__(self):
        self.schedule_data = {}
        self.topics_data = {}
        self._load_schedule()
        self._load_topics()

    def _load_topics(self):
        """data/NPC_topics.json 로드"""
        import json
        import os
        
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        topics_path = os.path.join(base_dir, "data", "NPC_topics.json")
        
        if not os.path.exists(topics_path):
            print(f"⚠️ [Topics] File not found: {topics_path}")
            return
            
        try:
            with open(topics_path, "r", encoding="utf-8") as f:
                self.topics_data = json.load(f)
            print(f"[Topics] Loaded NPC topics.")
        except Exception as e:
            print(f"⚠️ [Topics] Load failed: {e}")

    def _get_random_topic(self) -> str:
        """NPC_topics.json에서 랜덤 주제 선정"""
        import random
        if not self.topics_data or "npc_dialogue_sessions" not in self.topics_data:
            return "오늘의 날씨와 기분에 대해"
        
        sessions = self.topics_data["npc_dialogue_sessions"]
        if not sessions:
            return "서로의 안부 묻기"
            
        # 1. 랜덤 카테고리
        session = random.choice(sessions)
        # 2. 랜덤 토픽
        if not session.get("topics"):
            return f"{session.get('category')}에 대한 대화"
            
        topic = random.choice(session["topics"])
        return f"[{session.get('category')}] {topic['title']}: {topic['summary']} (상황: {topic['context']})"

    @traceable(run_type="chain", name="NPC_Conversation_AutoPlay")
    async def start_auto_conversation(
        self,
        topic: str,
        npc_ids: List[str],
        num_turns: int = 5
    ) -> ConversationResponse:
        """
        NPC-only 자동 대화 (유저 참여 X)
        
        - NPC들은 'Good' 상태(친밀도 60) 페르소나를 강제로 사용합니다.
        - 대화 중 상태(친밀도/신뢰도)는 변하지 않습니다.
        """
        # 랜덤 주제 선정 (입력된 topic이 'random'이거나 비어있으면)
        if not topic or topic == "random":
            topic = self._get_random_topic()
            print(f"[Conversation] Random Topic Selected: {topic}")

        turns: List[ConversationTurn] = []
        conversation_history: List[Dict[str, str]] = [
            self._build_topic_history_entry(topic)
        ]
        collected_states: Dict[str, Dict] = {}
        
        # NPC 간 대화는 친밀도/신뢰도 변화 없음 & Good(60) 페르소나 강제
        forced_state = {"friendly": 60, "faith": 60}

        for turn_idx in range(num_turns):
            # NPC 순서 결정 (라운드 로빈)
            current_npc_id = npc_ids[turn_idx % len(npc_ids)]

            # 이전 턴의 마지막 발언을 기반으로 메시지 구성
            if turn_idx == 0:
                # 첫 턴: 주제로 대화 시작 — 다른 NPC가 주제를 던진 것처럼 구성
                message = f"[대화 주제: {topic}] 이 주제에 대해 이야기해 봐."
            else:
                # 이후: 이전 NPC의 발언을 입력으로 전달
                prev_turn = turns[-1]
                message = prev_turn.content

            # LLM으로 NPC 응답 생성
            result = await llm_engine.ask(
                npc_id=current_npc_id,
                message=message,
                history=conversation_history,
                update_state=False,        # 상태 업데이트 끔
                forced_state=forced_state  # Good 페르소나 강제
            )

            npc_response = result.get("response", "")
            analysis = result.get("analysis", {})
            state = result.get("state", {})
            
            if state:
                collected_states[current_npc_id] = state

            # 한국어 이름 가져오기
            korean_name = self._get_npc_korean_name(current_npc_id)

            turn = ConversationTurn(
                speaker=korean_name,
                speaker_id=current_npc_id,
                content=npc_response,
                analysis=analysis
            )
            turns.append(turn)

            # 히스토리에 추가 (다음 NPC에게 전달)
            conversation_history.append({
                "speaker": current_npc_id,
                "content": npc_response
            })

            print(f"[Conversation] Turn {turn_idx + 1}/{num_turns}: "
                  f"{korean_name}({current_npc_id}) 응답 완료")

        return ConversationResponse(
            topic=topic,
            turns=turns,
            npc_states=self._resolve_npc_states(npc_ids, turns, collected_states)
        )

    @traceable(run_type="chain", name="NPC_Conversation_UserReply")
    async def process_user_reply(
        self,
        topic: str,
        npc_ids: List[str],
        user_message: str,
        history: Optional[List[Dict[str, Any]]] = None
    ) -> ConversationResponse:
        """
        User+NPC 대화 (유저 참여 O)

        유저 메시지를 받고, 각 NPC가 순서대로 반응합니다.
        클라이언트는 유저가 새 메시지를 보낼 때마다 이 메서드를 호출합니다.

        Args:
            topic: 대화 주제
            npc_ids: 참여 NPC ID 목록
            user_message: 유저의 발언
            history: 이전 대화 턴들
        """
        # 히스토리 구성
        conversation_history = self._build_conversation_history(
            topic, history or []
        )

        # 유저 발언을 히스토리에 추가
        conversation_history.append({
            "speaker": "user",
            "content": user_message
        })

        turns: List[ConversationTurn] = []
        collected_states: Dict[str, Dict] = {}  # 상태 수집용

        # 유저 턴 기록
        user_turn = ConversationTurn(
            speaker="user",
            speaker_id="user",
            content=user_message,
            analysis=None
        )
        turns.append(user_turn)

        # 각 NPC가 순서대로 응답
        for npc_id in npc_ids:
            result = await llm_engine.ask(
                npc_id=npc_id,
                message=user_message,
                history=conversation_history
            )

            npc_response = result.get("response", "")
            analysis = result.get("analysis", {})
            state = result.get("state", {})
            
            if state:
                collected_states[npc_id] = state

            korean_name = self._get_npc_korean_name(npc_id)

            turn = ConversationTurn(
                speaker=korean_name,
                speaker_id=npc_id,
                content=npc_response,
                analysis=analysis
            )
            turns.append(turn)

            # 이 NPC의 응답도 히스토리에 추가 (다음 NPC가 참고)
            conversation_history.append({
                "speaker": npc_id,
                "content": npc_response
            })

            print(f"[Conversation] {korean_name}({npc_id}) 응답 완료")

        return ConversationResponse(
            topic=topic,
            turns=turns,
            npc_states=self._resolve_npc_states(npc_ids, turns, collected_states)
        )

    def _get_npc_korean_name(self, npc_id: str) -> str:
        """NPC ID에서 한국어 이름 조회"""
        # LLMEngine의 pipeline에서 korean_name 가져오기
        if npc_id in llm_engine.pipelines:
            return llm_engine.pipelines[npc_id].korean_name

        # 파이프라인이 없으면 prompt_loader에서 직접 조회
        try:
            pipeline = llm_engine._get_or_create_pipeline(npc_id)
            return pipeline.korean_name
        except Exception:
            pass

        # 최종 fallback: NPC ID 매핑
        NPC_NAME_MAP = {
            "NPC_KWAK_01": "곽빙어",
            "NPC_CHEONG_02": "청갈치",
            "NPC_PARK_03": "박복어",
            "NPC_JEON_04": "전광어",
        }
        return NPC_NAME_MAP.get(npc_id, npc_id)

    def _resolve_npc_states(
        self, 
        npc_ids: List[str], 
        turns: List[ConversationTurn],
        collected_states: Optional[Dict[str, Dict]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        NPC 상태 결정
        1. collected_states (LLM 응답에서 직접 추출) 확인
        2. 없으면 llm_engine.get_npc_state (로컬) 확인
        3. 없으면 기본값
        """
        states = {}
        collected_states = collected_states or {}
        
        for npc_id in npc_ids:
            # 1. 수집된 상태 우선
            if npc_id in collected_states:
                states[npc_id] = collected_states[npc_id]
                continue
                
            # 2. 로컬 파이프라인 상태 (Local 모드용)
            state = llm_engine.get_npc_state(npc_id)
            if state:
                states[npc_id] = state
            else:
                # 3. 기본값 (Proxy 모드이고 NPC가 이번 턴에 말을 안 했다면 어쩔 수 없음)
                # 다만 start_auto_conversation의 경우 collected_states를 넘겨주지 못하므로 
                # (메서드 구조상) 이 부분이 취약함. 
                # start_auto_conversation도 수정해야 함.
                states[npc_id] = {"friendly": 50, "faith": 50}
        return states
        return states

    def __init__(self):
        self.schedule_data = {}
        self.topics_data = {}
        self._load_schedule()
        self._load_topics()

    def _load_schedule(self):
        """data/schedule.json 로드"""
        import json
        import os
        
        # 프로젝트 루트 경로 추정 (app/services/.. -> ../../)
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        schedule_path = os.path.join(base_dir, "data", "schedule.json")
        
        if not os.path.exists(schedule_path):
            print(f"⚠️ [Schedule] File not found: {schedule_path}")
            return
            
        try:
            with open(schedule_path, "r", encoding="utf-8") as f:
                self.schedule_data = json.load(f)
            print(f"[Schedule] Loaded {len(self.schedule_data)} NPCs schedules.")
        except Exception as e:
            print(f"⚠️ [Schedule] Load failed: {e}")

    async def trigger_scheduled_conversations(
        self,
        day_index: int,
        session: str
    ) -> List[ConversationResponse]:
        """
        스케줄 기반 NPC 자동 대화 트리거
        
        1. 스케줄 로드 (init에서 수행됨)
        2. NPC별 현재(Day, Session) 위치 파악
        3. 동일 장소에 있는 NPC 그룹화
        4. 2명 이상 모인 그룹에 대해 start_auto_conversation 실행
        5. 결과 저장 (장기 기억)
        """
        if not self.schedule_data:
            self._load_schedule()

        schedule_data = self.schedule_data
        location_map: Dict[str, List[str]] = {} # {location: [npc_ids]}
        
        # 1. 위치 파악 및 그룹화
        for npc_id, schedule in schedule_data.items():
            # Day별 스케줄 확인 (없으면 default)
            day_key = str(day_index)
            daily_schedule = schedule.get(day_key, schedule.get("default", {}))
            
            # Session별 위치 확인
            location = daily_schedule.get(session)
            
            if location:
                if location not in location_map:
                    location_map[location] = []
                location_map[location].append(npc_id)
                
        results = []
        
        # 2. 그룹별 대화 생성
        for location, npc_ids in location_map.items():
            if len(npc_ids) < 2:
                continue
                
            print(f"[Schedule] {day_index}일차 {session} - {location}: {npc_ids} 대화 시작")
            
            # 주제 자동 생성 (간단히)
            topic = f"{location}에서의 상황과 서로의 안부"
            
            # 대화 생성
            # TODO: num_turns, topic 등을 좀 더 다채롭게?
            response = await self.start_auto_conversation(
                topic=topic,
                npc_ids=npc_ids,
                num_turns=5
            )
            
            # 3. 장기 기억 저장 (Observer Memory)
            # 이 대화는 '누군가(아마도 플레이어?)가 목격함' 혹은 '전지적 시점'으로 저장
            conversation_text = f"[Event: {day_index}일차 {session} @ {location}]\n"
            conversation_text += f"참여자: {', '.join(npc_ids)}\n"
            for turn in response.turns:
                conversation_text += f"{turn.speaker}: {turn.content}\n"
            
            # 요약 생성 (StoryAgent)
            from app.agents.story_agent import story_agent
            summary = story_agent.summarize_event(conversation_text)
            print(f"[Schedule] Event Surveyed: {summary}")

            from app.core.memory import memory_manager
            memory_manager.add_memory(
                text=summary, # 요약된 내용을 임베딩 및 저장
                metadata={
                    "memory_type": "scheduled_event",
                    "day_index": day_index,
                    "session": session,
                    "location": location,
                    "participants": npc_ids,
                    "full_log": conversation_text # 원본 대화는 메타데이터에 보관
                }
            )
            print(f"[Schedule] 대화 저장 완료 ({location})")
            
            results.append(response)
            
        return results
conversation_service = ConversationService()
