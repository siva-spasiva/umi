"""
NPC 대화 통합 파이프라인
- IntentAnalyzer + LangChain LLM 결합
- RAG 기반 페르소나 및 기억 검색
- RAG
"""

from typing import Dict, Any, Optional, Type, List
from app.agents.npc_dialogue_engine import (
    IntentAnalyzer, 
    NPCState,
    get_relationship_bucket,
    sanitize_npc_response,
    format_control_signal
)

# LangChain 관련 import
from langchain_core.runnables import Runnable
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.retrievers import BaseRetriever


# ============================================================
# 통합 파이프라인
# ============================================================

class NPCDialoguePipeline:
    """
    NPC 대화 생성 통합 파이프라인
    
    워크플로우:
    1. 사용자 입력 → IntentAnalyzer → 의도/감정 분석
    2. 분석 결과 + 현재 상태 → 컨트롤 시그널 생성
    3. RAG 검색 (페르소나 + 관련 기억)
    4. 시스템 프롬프트 구성 (페르소나 + 컨트롤 시그널)
    5. DialogueGenerator → 대화 생성
    6. 후처리 (불필요한 텍스트 제거)
    7. 상태 업데이트
    """
    
    def __init__(
        self,
        analyzer: IntentAnalyzer,
        llm: Runnable, # DialogueGenerator 대신 LangChain Runnable(LLM)을 받음
        retriever: Optional[BaseRetriever] = None, # RAG용 검색기 추가
        npc_id: str = "CHEONGGALCHI",
        initial_state: NPCState = None
    ):
        self.analyzer = analyzer
        self.llm = llm
        self.retriever = retriever
        self.npc_id = npc_id
        self.state = initial_state or NPCState()
        
        # 디버그 모드
        self.debug = False
    
    def _build_system_prompt(
        self,
        user_message: str,
        analysis: Dict[str, Any],
        context: str = ""
    ) -> str:
        """
        시스템 프롬프트 구성
        
        구성 요소:
        1. RAG 컨텍스트 (페르소나 정의 + 기억)
        2. 컨트롤 시그널 (분석 결과)
        3. 출력 제약
        """
        # 관계도 버킷 계산 (프롬프트에 힌트로 제공)
        bucket = get_relationship_bucket(self.state.friendly)
        
        # 컨트롤 시그널
        control_signal = format_control_signal(
            analysis["reason_tags"],
            analysis["friendly_delta"],
            analysis["faith_delta"]
        )
        
        # 한국어 이름 매핑
        npc_names = {
            "JeongGwangeo": "전광어",
            "CHEONGGALCHI": "청갈치",
            "ParkBokeo": "박복어",
            "GwakBingeo":"곽빙어"
        }
        korean_name = npc_names.get(self.npc_id, self.npc_id)

        # RAG 컨텍스트 블록 구성
        # 검색된 문서가 없으면 기본 페르소나 요청
        context_block = f"[BASIC_SETTING]\nYou are {korean_name} ({self.npc_id}). Converse according to the given situation."
        if context:
            context_block = f"\n[RETRIEVED_INFO (Persona/Memory)]\n{context}\n"

        # 시스템 프롬프트 조합
        system_prompt = f"""{context_block}

{control_signal}

[CURRENT_RELATIONSHIP]
- Friendly: {self.state.friendly}/100
- Faith: {self.state.faith}/100

[OUTPUT_RULES]
- Output ONLY {korean_name}'s dialogue.
- MUST SPEAK IN KOREAN.
- NO options, explanations, summaries, markdown, or code blocks.
- End the last sentence with a counter-question, suggestion, or implying next action.
"""
        return system_prompt.strip()
    
    def chat(
        self,
        user_message: str,
        history: Optional[List[Dict[str, str]]] = None,
        max_new_tokens: int = 160,
        do_sample: bool = False
    ) -> Dict[str, Any]:
        """
        대화 생성
        
        Args:
            user_message: 사용자 입력
            history: 대화 내역 [{"speaker": "user"|"npc", "content": "..."}, ...]
            max_new_tokens: 생성 토큰 수
            do_sample: 샘플링 사용 여부
            
        Returns:
            {
                "npc_response": str,
                "state": Dict[str, int],
                "analysis": Dict[str, Any],
                "debug": Optional[Dict]
            }
        """
        from typing import List, Dict

        # 1. 의도 분석
        analysis = self.analyzer.analyze(user_message)
        
        # 2. 상태 업데이트
        self.state.apply_delta(
            analysis["friendly_delta"],
            analysis["faith_delta"]
        )
        
        # 3. RAG: 관련 정보 검색 (페르소나 + 기억)
        # 검색 쿼리에 NPC ID를 포함하여 해당 NPC의 페르소나를 우선적으로 찾도록 유도
        context_text = ""
        if self.retriever:
            try:
                # 쿼리 확장: "NPC_ID 페르소나" + 사용자 질문
                search_query = f"{self.npc_id} 성격 특징. {user_message}"
                docs = self.retriever.invoke(search_query)
                context_text = "\n".join([doc.page_content for doc in docs])
            except Exception as e:
                print(f"⚠️ [RAG] 검색 실패: {e}")

        # 4. 시스템 프롬프트 생성 (컨텍스트 포함)
        npc_names = {
            "JeongGwangeo": "전광어",
            "CHEONGGALCHI": "청갈치",
            "ParkBokeo": "박복어",
            "GwakBingeo":"곽빙어"
        }
        korean_name = npc_names.get(self.npc_id, self.npc_id)

        system_prompt = self._build_system_prompt(user_message, analysis, context=context_text)
        
        # 5. 대화 생성 프롬프트 구성 (Gemma 2 포맷 적용)
        # 구조: System(User) -> Ack(Model) -> History -> Current(User) -> Model
        
        full_prompt = f"<start_of_turn>user\n{system_prompt}<end_of_turn>\n"
        full_prompt += f"<start_of_turn>model\n확인했습니다. {korean_name}의 페르소나로 대화하겠습니다.<end_of_turn>\n"
        
        # 대화 이력 추가
        if history:
            for msg in history[-10:]: # 최근 10개만 사용
                role = "user" if msg.get("speaker") == "user" else "model"
                content = msg.get("content", "")
                full_prompt += f"<start_of_turn>{role}\n{content}<end_of_turn>\n"
        
        # 현재 사용자 메시지 추가
        full_prompt += f"<start_of_turn>user\n{{user_input}}<end_of_turn>\n<start_of_turn>model\n"

        prompt_template = PromptTemplate(input_variables=["user_input"], template=full_prompt)

        # 파이프라인 내에서 동적으로 체인 구성 및 실행
        chain = prompt_template | self.llm | StrOutputParser()

        # LangSmith에서 추적될 때, 이 invoke 호출이 기록됩니다.
        raw_response = chain.invoke({"user_input": user_message})
        
        # 6. 후처리
        npc_response = sanitize_npc_response(raw_response)
        
        # 7. 결과 구성
        result = {
            "npc_response": npc_response,
            "state": self.state.to_dict(),
            "analysis": {
                "reason_tags": analysis["reason_tags"],
                "friendly_delta": analysis["friendly_delta"],
                "faith_delta": analysis["faith_delta"],
                "relationship_bucket": get_relationship_bucket(self.state.friendly)
            }
        }
        
        # 디버그 정보
        if self.debug:
            result["debug"] = {
                "raw_response": raw_response,
                "system_prompt": system_prompt,
                "rag_context": context_text, # 디버그 시 검색된 내용 확인 가능
                "tag_probs": analysis["tag_probs"]
            }
        
        return result


# ============================================================
# 사용 예시
# ============================================================

if __name__ == "__main__":
    import os
    import sys
    
    # 프로젝트 루트 경로 추가 (직접 실행 시 필요)
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    from app.core.llm_factory import LLMFactory
    
    print("=== NPC Dialogue Pipeline Demo ===\n")
    
    # 1. 컴포넌트 초기화
    print("[1/3] Loading IntentAnalyzer...")
    analyzer = IntentAnalyzer(
        encoder_model="monologg/koelectra-base-v3-discriminator",
        checkpoint_path="./NPC_model/best_model.pt",  # 실제 경로로 수정
        tag_threshold=0.35
    )
    
    print("[2/3] Loading LLM (via LLMFactory)...")
    llm = LLMFactory.create_llm(model_key="npc")
    
    print("[3/3] Creating pipeline...")
    pipeline = NPCDialoguePipeline(
        analyzer=analyzer,
        llm=llm,
        npc_id="CHEONGGALCHI",
        initial_state=NPCState(friendly=50, faith=50)
    )
    
    # 디버그 모드 활성화 (선택)
    pipeline.debug = True
    
    print("\n=== 대화 시작 ===")
    print("명령어: /debug on|off, /state, exit")
    print()
    
    # 2. 대화 루프
    while True:
        user_input = input("플레이어: ").strip()
        
        if not user_input:
            continue
        
        if user_input.lower() == "exit":
            print("대화를 종료합니다.")
            break
        
        # 명령어 처리
        if user_input.startswith("/"):
            if user_input == "/debug on":
                pipeline.debug = True
                print("[CMD] 디버그 모드: ON")
            elif user_input == "/debug off":
                pipeline.debug = False
                print("[CMD] 디버그 모드: OFF")
            elif user_input == "/state":
                print(f"[CMD] 현재 상태: {pipeline.state.to_dict()}")
            else:
                print("[CMD] 알 수 없는 명령어")
            continue
        
        # 대화 생성
        try:
            result = pipeline.chat(user_input)
            
            # 출력
            print(f"\n[{pipeline.npc_id}]")
            print(result["npc_response"])
            print()
            print(f"상태: {result['state']}")
            print(f"분석: 태그={result['analysis']['reason_tags']}, "
                  f"호감={result['analysis']['friendly_delta']:+d}, "
                  f"신뢰={result['analysis']['faith_delta']:+d}")
            
            # 디버그 정보
            if pipeline.debug and "debug" in result:
                print(f"\n[디버그]")
                print(f"태그 확률 (상위 5개):")
                top5 = sorted(
                    result["debug"]["tag_probs"].items(),
                    key=lambda x: -x[1]
                )[:5]
                for tag, prob in top5:
                    print(f"  {tag}: {prob:.3f}")
            
            print()
            
        except Exception as e:
            print(f"[오류] {e}")
            if pipeline.debug:
                import traceback
                traceback.print_exc()
