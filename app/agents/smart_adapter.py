"""
스마트 LLM 어댑터
- Local 환경: Ollama 자동 사용 (빠르고 편리)
- AWS 서버: HuggingFace Transformers 사용 (안정적)
- 자동 감지 및 폴백
"""

import os
import socket
from typing import Optional, Union
from npc_dialogue_engine import DialogueGenerator


def is_local_environment() -> bool:
    """
    로컬 환경인지 AWS 서버인지 감지
    
    감지 기준:
    1. 환경 변수 DEPLOYMENT_ENV 확인
    2. Ollama 서버 연결 가능 여부
    3. AWS 관련 환경 변수 존재 여부
    """
    # 1. 명시적 환경 변수 확인 (최우선)
    deployment_env = os.environ.get("DEPLOYMENT_ENV", "").lower()
    if deployment_env == "local":
        return True
    elif deployment_env in ["aws", "production", "server"]:
        return False
    
    # 2. AWS 환경 변수 확인
    aws_indicators = [
        "AWS_EXECUTION_ENV",
        "AWS_REGION",
        "ECS_CONTAINER_METADATA_URI",
        "AWS_LAMBDA_FUNCTION_NAME"
    ]
    
    if any(os.environ.get(key) for key in aws_indicators):
        print("[SmartAdapter] AWS environment detected")
        return False
    
    # 3. Ollama 서버 연결 테스트
    try:
        import httpx
        with httpx.Client(timeout=2.0) as client:
            response = client.get("http://localhost:11434/api/tags")
            if response.status_code == 200:
                print("[SmartAdapter] Ollama server detected (local)")
                return True
    except Exception:
        pass
    
    # 4. 기본값: 로컬 환경으로 가정
    return True


class SmartDialogueGenerator:
    """
    환경별 자동 전환 대화 생성기
    
    - Local: Ollama 사용 (빠름)
    - AWS: HuggingFace 사용 (안정적)
    
    환경 변수로 강제 지정 가능:
    - DEPLOYMENT_ENV=local  → Ollama 강제
    - DEPLOYMENT_ENV=aws    → HuggingFace 강제
    """
    
    def __init__(
        self,
        # HuggingFace 설정
        hf_model_name: str = "google/gemma-2-2b-it",
        hf_token: Optional[str] = None,
        use_4bit: bool = True,
        
        # Ollama 설정
        ollama_model_name: str = "gemma2:2b",
        ollama_base_url: str = "http://localhost:11434",
        
        # 환경 강제 지정 (None이면 자동 감지)
        force_environment: Optional[str] = None
    ):
        self.hf_model_name = hf_model_name
        self.hf_token = hf_token
        self.use_4bit = use_4bit
        self.ollama_model_name = ollama_model_name
        self.ollama_base_url = ollama_base_url
        
        # 환경 감지
        if force_environment:
            self.is_local = (force_environment.lower() == "local")
            print(f"[SmartAdapter] Forced environment: {'Local' if self.is_local else 'AWS'}")
        else:
            self.is_local = is_local_environment()
        
        # 적절한 생성기 초기화
        self.generator = self._initialize_generator()
        self.backend = "Ollama" if self.is_local else "HuggingFace"
        
        print(f"✅ [SmartAdapter] Using {self.backend}")
    
    def _initialize_generator(self):
        """환경에 맞는 생성기 초기화"""
        
        if self.is_local:
            # Local: Ollama 시도
            try:
                from ollama_adapter import OllamaDialogueGenerator
                print("[SmartAdapter] Initializing Ollama...")
                return OllamaDialogueGenerator(
                    model_name=self.ollama_model_name,
                    base_url=self.ollama_base_url
                )
            except Exception as e:
                print(f"⚠️ [SmartAdapter] Ollama failed: {e}")
                print("   Falling back to HuggingFace...")
        
        # AWS 또는 Ollama 실패: HuggingFace
        print("[SmartAdapter] Initializing HuggingFace...")
        return DialogueGenerator(
            model_name=self.hf_model_name,
            hf_token=self.hf_token,
            use_4bit=self.use_4bit
        )
    
    def generate(
        self,
        system_prompt: str,
        user_message: str,
        max_new_tokens: int = 160,
        **kwargs
    ) -> str:
        """
        대화 생성 (인터페이스 통일)
        
        내부적으로 Ollama 또는 HuggingFace 사용
        """
        return self.generator.generate(
            system_prompt=system_prompt,
            user_message=user_message,
            max_new_tokens=max_new_tokens,
            **kwargs
        )
    
    def get_backend_info(self) -> dict:
        """현재 사용 중인 백엔드 정보"""
        return {
            "backend": self.backend,
            "is_local": self.is_local,
            "model": self.ollama_model_name if self.is_local else self.hf_model_name
        }


# ============================================================
# 설정 헬퍼 함수
# ============================================================

def get_smart_generator_config() -> dict:
    """
    환경 변수에서 설정 읽기
    
    환경 변수:
    - DEPLOYMENT_ENV: local, aws, production
    - NPC_LLM_MODEL: HuggingFace 모델 이름
    - HF_TOKEN: HuggingFace 토큰
    - USE_4BIT: 4bit 양자화 사용 여부
    - OLLAMA_MODEL: Ollama 모델 이름
    - OLLAMA_URL: Ollama 서버 URL
    """
    return {
        "hf_model_name": os.environ.get("NPC_LLM_MODEL", "google/gemma-2-2b-it"),
        "hf_token": os.environ.get("HF_TOKEN"),
        "use_4bit": os.environ.get("USE_4BIT", "true").lower() == "true",
        "ollama_model_name": os.environ.get("OLLAMA_MODEL", "gemma2:2b"),
        "ollama_base_url": os.environ.get("OLLAMA_URL", "http://localhost:11434"),
        "force_environment": os.environ.get("DEPLOYMENT_ENV")
    }


# ============================================================
# 테스트 코드
# ============================================================

if __name__ == "__main__":
    print("=== Smart Adapter Test ===\n")
    
    # 환경 감지
    is_local = is_local_environment()
    print(f"환경: {'Local' if is_local else 'AWS/Server'}\n")
    
    # 생성기 초기화
    config = get_smart_generator_config()
    generator = SmartDialogueGenerator(**config)
    
    # 백엔드 정보
    info = generator.get_backend_info()
    print(f"\n백엔드: {info['backend']}")
    print(f"모델: {info['model']}\n")
    
    # 간단한 테스트
    system_prompt = """당신은 '청갈치'입니다.
계산적이고 정보를 거래 대상으로 봅니다.
2-3문장으로 답하세요."""
    
    response = generator.generate(
        system_prompt=system_prompt,
        user_message="안녕? 오늘 기분 어때?",
        max_new_tokens=100
    )
    
    print(f"[청갈치] {response}")
