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

    @traceable(run_type="chain", name="NPC_Conversation_AutoPlay")
    async def start_auto_conversation(
        self,
        topic: str,
        npc_ids: List[str],
        num_turns: int = 5
    ) -> ConversationResponse:
        """
        NPC-only 자동 대화 (유저 참여 X)

        NPC들이 번갈아가며 주제에 대해 num_turns만큼 대화합니다.
        첫 번째 NPC가 주제에 대해 먼저 발언하고,
        이후 NPC들이 이전 발언에 반응하며 대화를 이어갑니다.

        Args:
            topic: 대화 주제
            npc_ids: 참여 NPC ID 목록
            num_turns: 생성할 대화 턴 수
        """
        turns: List[ConversationTurn] = []
        conversation_history: List[Dict[str, str]] = [
            self._build_topic_history_entry(topic)
        ]
        collected_states: Dict[str, Dict] = {}

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
                history=conversation_history
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


conversation_service = ConversationService()
