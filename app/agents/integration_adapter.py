"""
LangChain 기반 통합 어댑터

- IntentAnalyzer: 기존 의도 분석 모델 로드
- LLMFactory: LangChain과 호환되는 LLM(로컬, Ollama) 로드
- 이 모듈의 인스턴스는 llm_engine.py에서 사용되어 전체 파이프라인을 구성합니다.
"""

import asyncio
import os
from typing import List, Dict, Optional
from npc_dialogue_engine import IntentAnalyzer, NPCState
from npc_pipeline import NPCDialoguePipeline

# LangChain LLM 로더
from app.core.llm_factory import LLMFactory


# ============================================================
# 1. NpcAgent 호환 래퍼
# ============================================================

class NpcAgent:
    """
    기존 npc_agent.py와 호환되는 인터페이스
    
    변경 사항:
    - 의도 분석기(analyzer)와 LangChain LLM(llm)을 로드하여 속성으로 가집니다.
    - 실제 대화 생성 로직은 NPCDialoguePipeline으로 이전되었습니다.
    """
    
    def __init__(self):
        print("[NpcAgent] Initializing with LangChain integration...")
        
        # 경로 설정
        base_dir = os.path.dirname(os.path.abspath(__file__))
        local_model_path = os.path.join(base_dir, "NPC_model")
        checkpoint_path = os.path.join(local_model_path, "best_model.pt")
        
        if not os.path.exists(checkpoint_path):
            print(f"⚠️ [NpcAgent] Checkpoint not found: {checkpoint_path}")
            print(f"   Using base model without fine-tuning.")
            checkpoint_path = None
        
        # 의도 분석기 초기화 (항상 사용)
        print("[NpcAgent] Loading IntentAnalyzer...")
        self.analyzer = IntentAnalyzer(
            encoder_model="monologg/koelectra-base-v3-discriminator",
            checkpoint_path=checkpoint_path,
            tag_threshold=0.35
        )
        
        # LangChain LLM 로드
        self.llm = None
        self.generation_enabled = False
        try:
            # LLMFactory가 .env 설정에 따라 적절한 LLM을 로드합니다.
            self.llm = LLMFactory.create_llm(model_key="npc")
            self.generation_enabled = True
            print("✅ [NpcAgent] LangChain LLM loaded successfully.")
        except Exception as e:
            print(f"⚠️ [NpcAgent] LLM loading failed: {e}")
            print(f"   Only analysis mode available.")
        
        print(f"✅ [NpcAgent] Ready (generation: {self.generation_enabled})")
    
    def predict(self, text: str) -> Dict:
        """
        의도 분석 (기존 호환)
        
        Args:
            text: 입력 텍스트
            
        Returns:
            분석 결과 딕셔너리
        """
        return self.analyzer.analyze(text)


# 싱글톤 인스턴스
npc_agent = NpcAgent()


# ============================================================
# 2. LLMEngine 호환 래퍼
# ============================================================

class LLMEngine:
    """
    기존 llm_engine.py와 호환되는 인터페이스
    
    변경 사항:
    - 이제 IntentAnalyzer + DialogueGenerator 파이프라인 사용
    - 상태 관리 추가
    """
    
    def __init__(self):
        self.agent = npc_agent  # 호환성 유지
        
        # 파이프라인 생성 (NPC별)
        self.pipelines: Dict[str, NPCDialoguePipeline] = {}
        
        print("[LLMEngine] Initialized with pipeline architecture")
    
    def _get_or_create_pipeline(self, npc_id: str) -> NPCDialoguePipeline:
        """NPC별 파이프라인 가져오기 또는 생성"""
        if npc_id not in self.pipelines:
            if not self.agent.generation_enabled:
                raise RuntimeError("대화 생성이 비활성화되어 있습니다.")
            
            # 새 파이프라인 생성
            self.pipelines[npc_id] = NPCDialoguePipeline(
                analyzer=self.agent.analyzer,
                llm=self.agent.llm,
                npc_id=npc_id,
                personas=CHUNG_GALCHI_PERSONAS,  # NPC별로 다른 페르소나 사용 가능
                initial_state=NPCState(friendly=50, faith=50)
            )
        
        return self.pipelines[npc_id]
    
    async def ask(
        self,
        npc_id: str,
        message: str,
        history: Optional[List[Dict]] = None
    ) -> str:
        """
        NPC에게 질문하고 응답 받기
        
        Args:
            npc_id: NPC 식별자
            message: 사용자 메시지
            history: 대화 히스토리 (현재 미사용, 향후 확장 가능)
            
        Returns:
            NPC 응답
        """
        try:
            # 파이프라인 가져오기
            pipeline = self._get_or_create_pipeline(npc_id)
            
            # 대화 생성 (비동기 래핑)
            result = await asyncio.to_thread(
                pipeline.chat,
                message,
                max_new_tokens=160,
                do_sample=False
            )
            
            # 응답 반환
            response = result["npc_response"]
            
            # 상태 변화 로깅
            analysis = result["analysis"]
            print(f"[LLMEngine] {npc_id} 응답 완료")
            print(f"  - 호감도: {result['state']['friendly']} ({analysis['friendly_delta']:+d})")
            print(f"  - 신뢰도: {result['state']['faith']} ({analysis['faith_delta']:+d})")
            print(f"  - 태그: {', '.join(analysis['reason_tags']) or 'NONE'}")
            
            return response
            
        except asyncio.TimeoutError:
            print(f"⚠️ [LLMEngine] {npc_id} 응답 시간 초과")
            return "시스템: (응답 시간이 초과되었습니다.)"
        except Exception as e:
            print(f"⚠️ [LLMEngine] 오류: {e}")
            return "시스템: (오류가 발생했습니다.)"
    
    def get_npc_state(self, npc_id: str) -> Optional[Dict]:
        """NPC 현재 상태 조회"""
        if npc_id in self.pipelines:
            return self.pipelines[npc_id].state.to_dict()
        return None
    
    def reset_npc_state(self, npc_id: str):
        """NPC 상태 초기화"""
        if npc_id in self.pipelines:
            self.pipelines[npc_id].state = NPCState(friendly=50, faith=50)
            print(f"[LLMEngine] {npc_id} 상태 초기화")


# 싱글톤 인스턴스
llm_engine = LLMEngine()


# ============================================================
# 3. 사용 예시
# ============================================================

async def test_integration():
    """통합 테스트"""
    print("\n=== Integration Test ===\n")
    
    # 기존 방식과 동일하게 사용
    response = await llm_engine.ask(
        npc_id="청갈치",
        message="안녕? 오늘 기분 어때?"
    )
    
    print(f"[청갈치] {response}\n")
    
    # 상태 확인
    state = llm_engine.get_npc_state("청갈치")
    print(f"현재 상태: {state}\n")


if __name__ == "__main__":
    # asyncio 테스트
    asyncio.run(test_integration())
