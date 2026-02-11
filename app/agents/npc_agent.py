import os
from typing import Dict
from app.core.config import settings
from app.agents.npc_dialogue_engine import IntentAnalyzer, DialogueGenerator

class NpcAgent:
    """
    기존 npc_agent.py와 호환되는 인터페이스
    
    변경 사항:
    - generate() 메서드: 이제 실제 대화 생성 지원
    - predict() 메서드: 의도 분석만 수행
    """
    
    def __init__(self):
        # GPU Proxy 모드: 모델 로드 건너뛰기 (EC2에서 실행)
        if settings.USE_GPU_PROXY:
            print("[NpcAgent] GPU Proxy mode — skipping local model loading")
            self.analyzer = None
            self.generator = None
            self.generation_enabled = False
            self.llm = None
            return

        print("[NpcAgent] Initializing with new architecture...")
        
        # 경로 설정
        base_dir = os.path.dirname(os.path.abspath(__file__))
        local_model_path = os.path.join(base_dir, "NPC_model")
        checkpoint_path = os.path.join(local_model_path, "best_model.pt")
        
        if not os.path.exists(checkpoint_path):
            print(f"⚠️ [NpcAgent] Checkpoint not found: {checkpoint_path}")
            print(f"   Using base model without fine-tuning.")
            checkpoint_path = None
        
        # 의도 분석기 초기화
        self.analyzer = IntentAnalyzer(
            encoder_model="monologg/koelectra-base-v3-discriminator",
            checkpoint_path=checkpoint_path,
            tag_threshold=0.35
        )
        
        # 대화 생성기 초기화
        hf_token = os.environ.get("HF_TOKEN")
        
        # LLM 모델 선택 (환경 변수로 제어)
        llm_model = os.environ.get("NPC_LLM_MODEL", "google/gemma-2-2b-it")
        use_4bit = os.environ.get("USE_4BIT", "true").lower() == "true"
        
        try:
            self.generator = DialogueGenerator(
                model_name=llm_model,
                hf_token=hf_token,
                use_4bit=use_4bit
            )
            self.generation_enabled = True
        except Exception as e:
            print(f"⚠️ [NpcAgent] DialogueGenerator failed to load: {e}")
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
        
        # 기본 페르소나 사용
        persona = """[NPC_ID]
이름: 청갈치
정체: 우미교의 신도이자 정보 거래상
[PERSONALITY]
실용적, 거래 지향적, 호기심 있음"""
        
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

# 싱글톤 인스턴스 생성
npc_agent = NpcAgent()