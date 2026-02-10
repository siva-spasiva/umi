import torch
from typing import Optional
from langchain_huggingface import HuggingFacePipeline
from langchain_community.chat_models import ChatOllama
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from app.core.config import settings

class LLMFactory:
    """
    설정에 따라 로컬 파인튜닝 모델(HuggingFace) 또는 Ollama 모델을
    LangChain Runnable 객체로 반환하는 팩토리 클래스
    """

    @staticmethod
    def create_llm(model_key: str = "npc", temperature: float = 0.1):
        """
        Args:
            model_key: 'npc', 'story', 'ga1', 'ga2' 중 하나
            temperature: 생성 다양성 조절
        Returns:
            LangChain BaseLLM or BaseChatModel
        """
        
        # 1. Ollama 사용 시 (로컬 서버)
        if settings.USE_OLLAMA:
            return ChatOllama(
                base_url=settings.OLLAMA_URL,
                model=settings.OLLAMA_MODEL,
                temperature=temperature
            )

        # 2. 로컬 파인튜닝 모델 로드 (HuggingFace Transformers)
        model_path = settings.get_model_path(model_key)
        
        if not model_path:
            raise ValueError(f"Model path for '{model_key}' is not configured in settings.")

        print(f"Loading local model from: {model_path} ...")

        # 토크나이저 및 모델 로드
        # (Apple Silicon인 경우 mps, CUDA인 경우 cuda, 그 외 cpu 자동 설정 권장)
        device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        
        try:
            tokenizer = AutoTokenizer.from_pretrained(model_path)
            model = AutoModelForCausalLM.from_pretrained(
                model_path,
                torch_dtype=torch.float16 if device != "cpu" else torch.float32,
                device_map="auto" if device != "cpu" else None,
                trust_remote_code=True
            )
        except OSError as e:
            raise OSError(f"Could not load model from {model_path}. Check if the path exists and is a valid HuggingFace model directory.") from e

        # HuggingFace Pipeline 생성
        pipe = pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            max_new_tokens=512,
            temperature=temperature,
            top_p=0.95,
            repetition_penalty=1.15,
            device_map="auto" if device != "cpu" else None
        )

        # LangChain 래퍼로 변환
        llm = HuggingFacePipeline(pipeline=pipe)
        
        return llm

# 사용 예시:
# from app.core.llm_factory import LLMFactory
# 
# npc_llm = LLMFactory.create_llm("npc")
# response = npc_llm.invoke("안녕하세요, 당신은 누구인가요?")
# print(response)