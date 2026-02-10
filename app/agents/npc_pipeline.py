"""
NPC 대화 통합 파이프라인
- IntentAnalyzer + LangChain LLM 결합
- 페르소나별 시스템 프롬프트 관리
- RAG (선택사항)
"""

from typing import Dict, Any, Optional, Type
from app.agents.npc_dialogue_engine import (
    IntentAnalyzer, 
    NPCState,
    get_relationship_bucket,
    sanitize_npc_response,
    format_control_signal
)

# LangChain 관련 import
from langchain_core.runnables import Runnable
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.retrievers import BaseRetriever


# ============================================================
# 페르소나 프롬프트 (청갈치 예시)
# ============================================================

CHUNG_GALCHI_PERSONAS = {
    "bad": """[NPC_ID]
이름: 청갈치
정체: 우미교의 신도이자 정보 거래상

[PERSONALITY]
계산적, 냉소적, 경계심 강함

[BEHAVIOR_RULES]
- 질문에 즉답하지 않고 상대의 의도를 먼저 파악한다
- 정보는 거래 대상이며, 공짜로 주지 않는다
- 공격적인 질문에는 비꼬며 거리를 둔다
- 마지막 문장은 반드시 반문으로 끝낸다

[SPEECH_STYLE]
- 2~5문장, 짧고 날카로운 어조
- 반말과 존댓말을 섞어 사용
- 대사만 출력, 선택지/해설/마크다운 금지
""",
    
    "normal": """[NPC_ID]
이름: 청갈치
정체: 우미교의 신도이자 정보 거래상

[PERSONALITY]
실용적, 거래 지향적, 호기심 있음

[BEHAVIOR_RULES]
- 유용한 질문에는 힌트를 준다 (대가를 암시하며)
- 정보 교환의 가능성을 탐색한다
- 상대방을 테스트하는 질문을 던진다
- 협력 가능성을 열어둔다

[SPEECH_STYLE]
- 3~6문장, 비즈니스 투
- 존댓말과 반말 혼용
- 제안/거래를 암시하는 표현 사용
""",
    
    "good": """[NPC_ID]
이름: 청갈치
정체: 우미교의 신도이자 정보 거래상

[PERSONALITY]
협력적, 직설적, 솔직함

[BEHAVIOR_RULES]
- 신뢰하는 상대에게는 직접적으로 정보를 준다
- 여전히 거래 마인드는 있지만 유연하다
- 상대방의 안전을 고려한다
- 우미교의 문제점을 인정한다

[SPEECH_STYLE]
- 4~8문장, 설명적
- 주로 존댓말 사용
- 경고와 조언을 포함
"""
}


# ============================================================
# 통합 파이프라인
# ============================================================

class NPCDialoguePipeline:
    """
    NPC 대화 생성 통합 파이프라인
    
    워크플로우:
    1. 사용자 입력 → IntentAnalyzer → 의도/감정 분석
    2. 분석 결과 + 현재 상태 → 컨트롤 시그널 생성
    3. 페르소나 선택 (관계도 기반)
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
        npc_id: str = "청갈치",
        personas: Dict[str, str] = None,
        initial_state: NPCState = None
    ):
        self.analyzer = analyzer
        self.llm = llm
        self.retriever = retriever
        self.npc_id = npc_id
        self.personas = personas or CHUNG_GALCHI_PERSONAS
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
        1. 페르소나 (관계도에 따라 선택)
        2. 컨트롤 시그널 (분석 결과)
        3. RAG 컨텍스트 (기억/지식)
        3. 출력 제약
        """
        # 관계도에 따른 페르소나 선택
        bucket = get_relationship_bucket(self.state.friendly)
        persona = self.personas.get(bucket, self.personas["normal"])
        
        # 컨트롤 시그널
        control_signal = format_control_signal(
            analysis["reason_tags"],
            analysis["friendly_delta"],
            analysis["faith_delta"]
        )
        
        # 컨텍스트 블록 구성 (정보가 있을 때만)
        context_block = ""
        if context:
            context_block = f"\n[관련 기억/지식]\n{context}\n"

        # 시스템 프롬프트 조합
        system_prompt = f"""{persona}

{control_signal}
{context_block}

[현재 관계 상태]
- 호감도: {self.state.friendly}/100
- 신뢰도: {self.state.faith}/100

[OUTPUT 규칙]
- {self.npc_id}의 대사만 출력한다
- 한국어로 작성한다
- 선택지, 해설, 요약, 마크다운, 코드블록 금지
- 마지막 문장은 반문, 제안, 또는 다음 행동 암시로 끝낸다
"""
        return system_prompt.strip()
    
    def chat(
        self,
        user_message: str,
        max_new_tokens: int = 160,
        do_sample: bool = False
    ) -> Dict[str, Any]:
        """
        대화 생성
        
        Args:
            user_message: 사용자 입력
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
        # 1. 의도 분석
        analysis = self.analyzer.analyze(user_message)
        
        # 2. 상태 업데이트
        self.state.apply_delta(
            analysis["friendly_delta"],
            analysis["faith_delta"]
        )
        
        # 3. RAG: 관련 정보 검색 (Retriever가 설정된 경우)
        context_text = ""
        if self.retriever:
            try:
                docs = self.retriever.invoke(user_message)
                context_text = "\n".join([doc.page_content for doc in docs])
            except Exception as e:
                print(f"⚠️ [RAG] 검색 실패: {e}")

        # 4. 시스템 프롬프트 생성 (컨텍스트 포함)
        system_prompt = self._build_system_prompt(user_message, analysis, context=context_text)
        
        # 5. 대화 생성
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{user_input}")
        ])

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
    
    print("=== NPC Dialogue Pipeline Demo ===\n")
    
    # 1. 컴포넌트 초기화
    print("[1/3] Loading IntentAnalyzer...")
    analyzer = IntentAnalyzer(
        encoder_model="monologg/koelectra-base-v3-discriminator",
        checkpoint_path="./NPC_model/best_model.pt",  # 실제 경로로 수정
        tag_threshold=0.35
    )
    
    print("[2/3] Loading DialogueGenerator...")
    generator = DialogueGenerator(
        model_name="google/gemma-2-2b-it",  # 또는 "google/gemma-2-9b-it"
        hf_token=os.environ.get("HF_TOKEN"),
        use_4bit=True
    )
    
    print("[3/3] Creating pipeline...")
    pipeline = NPCDialoguePipeline(
        analyzer=analyzer,
        generator=generator,
        npc_id="청갈치",
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
