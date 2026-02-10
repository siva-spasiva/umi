"""
기존 코드(llm_engine.py, npc_agent.py)와의 통합 어댑터

사용법:
1. 기존 코드를 이 파일로 교체
2. NPC_model/best_model.pt 경로 확인
3. 환경 변수 설정 (HF_TOKEN 등)

환경별 자동 전환:
- Local: Ollama 자동 사용 (빠름)
- AWS: HuggingFace 자동 사용 (안정적)
"""

import asyncio
import os
from typing import List, Dict, Optional
from npc_dialogue_engine import IntentAnalyzer, NPCState
from npc_pipeline import NPCDialoguePipeline, CHUNG_GALCHI_PERSONAS
from app.agents.smart_adapter import SmartDialogueGenerator, get_smart_generator_config


# ============================================================
# 1. NpcAgent 호환 래퍼
# ============================================================

class NpcAgent:
    """
    기존 npc_agent.py와 호환되는 인터페이스
    
    변경 사항:
    - generate() 메서드: 이제 실제 대화 생성 지원
    - predict() 메서드: 의도 분석만 수행
    - 환경별 자동 전환: Local(Ollama) / AWS(HuggingFace)
    """
    
    def __init__(self):
        print("[NpcAgent] Initializing with smart environment detection...")
        
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
        
        # 대화 생성기 초기화 (환경별 자동 전환)
        try:
            config = get_smart_generator_config()
            self.generator = SmartDialogueGenerator(**config)
            self.generation_enabled = True
            
            # 백엔드 정보 출력
            info = self.generator.get_backend_info()
            print(f"✅ [NpcAgent] Backend: {info['backend']} ({info['model']})")
            
        except Exception as e:
            print(f"⚠️ [NpcAgent] Generator initialization failed: {e}")
            print(f"   Only analysis mode available.")
            self.generator = None
            self.generation_enabled = False
        
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
    
    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 256,
        npc_id: str = "청갈치"
    ) -> str:
        """
        대화 생성 (기존 인터페이스 호환)
        
        Args:
            prompt: 프롬프트 (간단한 버전)
            max_new_tokens: 최대 토큰 수
            npc_id: NPC 이름
            
        Returns:
            생성된 대화
        """
        if not self.generation_enabled:
            return "⚠️ 대화 생성 기능이 비활성화되어 있습니다. (분석 모드만 지원)"
        
        # 간단한 프롬프트를 파이프라인 형식으로 변환
        # 기존: "당신은 '{npc_id}'입니다. ... User: {message}"
        # → 분석 없이 직접 생성
        
        # 기본 페르소나 사용
        persona = CHUNG_GALCHI_PERSONAS.get("normal", "")
        
        system_prompt = f"""{persona}

[OUTPUT 규칙]
- {npc_id}의 대사만 출력
- 선택지/해설/마크다운 금지
"""
        
        try:
            response = self.generator.generate(
                system_prompt=system_prompt,
                user_message=prompt,
                max_new_tokens=max_new_tokens,
                do_sample=False
            )
            return response
        except Exception as e:
            print(f"[ERROR] generate() failed: {e}")
            return "시스템: 대화 생성 중 오류가 발생했습니다."


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
                generator=self.agent.generator,
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
