"""
NPC 대화(Conversation) 서비스
- NPC-only: NPC끼리 주제를 가지고 자동 대화
- User+NPC: 유저와 NPC들이 함께 주제를 가지고 대화
"""

from typing import List, Dict, Any, Optional
import re
from app.agents.llm_engine import llm_engine
from app.schemas.conversation import (
    ConversationTurn,
    ConversationResponse,
)
from langsmith import traceable


class ConversationService:
    """NPC 대화 서비스"""

    _PLAYER_REF_PATTERN = re.compile(
        r"(플레이어|유저|사용자|외부인|새로\s*온|신입|그\s*사람|걔|쟤)",
        re.IGNORECASE
    )

    def _build_topic_history_entry(self, topic: str) -> Dict[str, str]:
        """주제를 대화 히스토리의 시스템 메시지 형태로 변환"""
        return {
            "speaker": "system",
            "content": f"[대화 주제] {topic}"
        }

    def _build_npc_only_rule_entry(self) -> Dict[str, str]:
        """NPC↔NPC 대화 모드 규칙"""
        return {
            "speaker": "system",
            "content": "[대화 규칙] 지금은 NPC끼리의 대화다. 플레이어/유저/외부인 언급은 피하고 현재 주제에 집중한다."
        }

    def _contains_player_reference(self, text: str) -> bool:
        return bool(self._PLAYER_REF_PATTERN.search(text or ""))

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
        self.topics_data = {}
        self._load_topics()

    def _load_topics(self):
        """data/NPC_topics.json 로드 및 VectorDB 인덱싱"""
        import json
        import os
        from app.core.memory import memory_manager
        from langchain_core.documents import Document
        
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        topics_path = os.path.join(base_dir, "data", "NPC_topics.json")
        
        if not os.path.exists(topics_path):
            print(f"⚠️ [Topics] File not found: {topics_path}")
            return
            
        try:
            with open(topics_path, "r", encoding="utf-8") as f:
                self.topics_data = json.load(f)
            print(f"[Topics] Loaded NPC topics JSON.")
            
            # VectorDB Indexing Check
            TOPIC_COLLECTION = "npc_topics"
            count = memory_manager.count(collection_name=TOPIC_COLLECTION)
            
            if count == 0:
                print(f"[Topics] Indexing topics to VectorDB ({TOPIC_COLLECTION})...")
                docs = []
                if "npc_dialogue_sessions" in self.topics_data:
                    for session in self.topics_data["npc_dialogue_sessions"]:
                        category = session.get("category", "General")
                        for topic in session.get("topics", []):
                            # 메타데이터 구성
                            meta = {
                                "topic_id": str(topic.get("id")),
                                "category": category,
                                "context": topic.get("context", "")
                            }
                            # 검색될 텍스트 구성 (Title + Description + Context)
                            text = f"[{category}] {topic.get('title')}: {topic.get('summary')}\n상황: {topic.get('context')}"
                            docs.append(Document(page_content=text, metadata=meta))
                
                if docs:
                    memory_manager.add_documents(docs, collection_name=TOPIC_COLLECTION)
                    print(f"[Topics] Indexed {len(docs)} topics.")
            else:
                print(f"[Topics] VectorDB already has {count} topics indexed.")
                
        except Exception as e:
            print(f"⚠️ [Topics] Load/Index failed: {e}")

    def _get_topic_from_vectordb(self, query: str = None) -> str:
        """VectorDB에서 주제 검색 (Retrieval-based)"""
        import random
        from app.core.memory import memory_manager
        
        TOPIC_COLLECTION = "npc_topics"
        
        # 쿼리가 없으면 랜덤성을 위해 섞은 키워드 사용
        if not query or query == "random":
            keywords = ["비밀", "의심", "탈출", "신체 변이", "교주", "식량", "외부인", "바다", "축복"]
            query = f"흥미로운 대화 주제, {random.choice(keywords)}"
            
        try:
            retriever = memory_manager.get_retriever(k=5, collection_name=TOPIC_COLLECTION)
            results = retriever.invoke(query)
            
            if not results:
                return "오늘의 날씨와 기분에 대해"
                
            # 검색 결과 중 랜덤 선택 (다양성)
            selected_doc = random.choice(results)
            return selected_doc.page_content
            
        except Exception as e:
            print(f"⚠️ [Topics] Retrieval failed: {e}")
            return "서로의 안부 묻기"

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
        - Topic이 없으면 VectorDB에서 검색하여 선정합니다.
        """
        # 랜덤 주제 선정 (입력된 topic이 'random'이거나 비어있으면)
        if not topic or topic == "random":
            topic = self._get_topic_from_vectordb(query="random")
            print(f"[Conversation] Retrieved Topic: {topic}")

        turns: List[ConversationTurn] = []
        conversation_history: List[Dict[str, str]] = [
            self._build_topic_history_entry(topic),
            self._build_npc_only_rule_entry(),
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
            if self._contains_player_reference(npc_response):
                npc_response = "그 얘기는 잠시 접어두고, 지금 주제부터 정리하자."
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



    async def trigger_scheduled_conversations(
        self,
        day_index: int,
        session: str
    ) -> List[ConversationResponse]:
        """
        스케줄 기반 NPC 자동 대화 트리거 (MongoDB 기반)
        
        1. ScheduleService를 통해 MongoDB에서 NPC 위치 조회
        2. 동일 장소에 있는 NPC 그룹화
        3. 2명 이상 모인 그룹에 대해 start_auto_conversation 실행
        4. 결과 저장 (장기 기억)
        """
        from app.services.schedule_service import schedule_service
        
        # session 문자열을 인덱스로 변환
        session_to_idx = {"morning": 1, "afternoon": 2, "evening": 3, "night": 4}
        session_idx = session_to_idx.get(session, 1)
        
        # MongoDB에서 NPC 위치 그룹 조회
        location_map = await schedule_service.map_npc_locations(day_index, session_idx)
                
        results = []
        
        # 그룹별 대화 생성
        for location, npc_ids in location_map.items():
            if len(npc_ids) < 2:
                continue
                
            print(f"[Schedule] {day_index}일차 {session} - {location}: {npc_ids} 대화 시작")
            
            # 주제 자동 생성 (간단히)
            topic = f"{location}에서의 상황과 서로의 안부"
            
            # 대화 생성
            response = await self.start_auto_conversation(
                topic=topic,
                npc_ids=npc_ids,
                num_turns=5
            )
            
            # 장기 기억 저장 (Observer Memory)
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
                text=summary,
                metadata={
                    "memory_type": "scheduled_event",
                    "day_index": day_index,
                    "session": session,
                    "location": location,
                    "participants": npc_ids,
                    "full_log": conversation_text
                }
            )
            print(f"[Schedule] 대화 저장 완료 ({location})")
            
            results.append(response)
            
        return results
conversation_service = ConversationService()
