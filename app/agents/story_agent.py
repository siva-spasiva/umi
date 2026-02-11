import os
import torch
import httpx
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import PeftModel
from app.core.config import settings

class StoryAgent:
    """
    Story Agent: LLM을 사용하여 스토리 진행, 대화 생성, 요약 등을 수행합니다.
    """
    def __init__(self):
        # GPU Proxy 모드: 모델 로드 건너뛰기
        if settings.USE_GPU_PROXY:
            print("[StoryAgent] GPU Proxy mode — skipping local model loading")
            self.model = None
            self.tokenizer = None
            return

        # 베이스 모델 ID (Qwen 2.5 7B Instruct)
        self.base_model_id = "Qwen/Qwen2.5-7B-Instruct"
        
        # [경로 자동 보정]
        base_dir = os.path.dirname(os.path.abspath(__file__))
        local_model_path = os.path.join(base_dir, "story_agent_model")

        # 어댑터 경로 설정 (우선순위: 환경변수 > 로컬 폴더 > None)
        if settings.STORY_MODEL_PATH and os.path.exists(settings.STORY_MODEL_PATH):
            self.adapter_path = settings.STORY_MODEL_PATH
        elif os.path.exists(local_model_path):
            print(f"📂 [StoryAgent] 로컬 모델 폴더 감지: {local_model_path}")
            self.adapter_path = local_model_path
        else:
            self.adapter_path = settings.STORY_MODEL_PATH
        
        if torch.cuda.is_available():
            self.device = "cuda"
        elif torch.backends.mps.is_available():
            self.device = "mps"
        else:
            self.device = "cpu"
            
        self.model = None
        self.tokenizer = None
        
        # 실제 모델 로드 시도 (GPU/CPU)
        self._load_model()

    def _load_model(self):
        """서버 시작 시 LLM을 메모리에 로드합니다."""
        try:
            # 토크나이저는 어댑터 경로에 있으면 거기서, 없으면 베이스 모델에서 로드
            tokenizer_path = self.adapter_path if (self.adapter_path and os.path.exists(self.adapter_path)) else self.base_model_id
            print(f"🔄 [StoryAgent] Loading Tokenizer: {tokenizer_path}...")
            
            self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_path, use_fast=True, trust_remote_code=True)
            if self.tokenizer.pad_token_id is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            # [메모리 최적화] 4bit 양자화 설정 (GPU가 있을 때만 적용)
            bnb_config = None
            if torch.cuda.is_available():
                bnb_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
                )
            
            print(f"🔄 [StoryAgent] Loading Base Model: {self.base_model_id}...")
            
            model_kwargs = {
                "device_map": "auto",
                "trust_remote_code": True,
                "torch_dtype": torch.bfloat16 if torch.cuda.is_available() and torch.cuda.is_bf16_supported() else torch.float16
            }
            
            if bnb_config:
                model_kwargs["quantization_config"] = bnb_config

            base_model = AutoModelForCausalLM.from_pretrained(
                self.base_model_id,
                **model_kwargs
            )
            
            if self.adapter_path and os.path.exists(self.adapter_path):
                print(f"🔄 [StoryAgent] Loading LoRA Adapter: {self.adapter_path}...")
                self.model = PeftModel.from_pretrained(base_model, self.adapter_path)
                print(f"✅ [StoryAgent] LoRA Adapter Loaded on {self.device}")
            else:
                print(f"⚠️ [StoryAgent] Adapter path not found. Using Base Model only.")
                self.model = base_model
                print(f"✅ [StoryAgent] Base Model Loaded on {self.device}")

            self.model.eval()
        except Exception as e:
            print(f"⚠️ [StoryAgent] 모델 로드 실패: {e}")
            if self.adapter_path and os.path.sep in self.adapter_path:
                print(f"   👉 (힌트) 로컬 경로 '{self.adapter_path}'가 정확한지 확인하세요. (현재 실행 위치: {os.getcwd()})")

    def generate(self, prompt: str, max_new_tokens: int = 256) -> str:
        """프롬프트를 입력받아 텍스트를 생성합니다."""
        # GPU Proxy 모드: AWS EC2 GPU 서버에 위임
        if settings.USE_GPU_PROXY:
            try:
                server_url = settings.GPU_SERVER_URL.rstrip("/")
                with httpx.Client(timeout=settings.GPU_PROXY_TIMEOUT) as client:
                    response = client.post(
                        f"{server_url}/infer/story",
                        json={"prompt": prompt, "max_new_tokens": max_new_tokens}
                    )
                    response.raise_for_status()
                    return response.json()["text"]
            except Exception as e:
                print(f"⚠️ [StoryAgent] GPU Proxy 오류: {e}")
                return "시스템: GPU 서버에 연결할 수 없습니다."

        try:
            # device_map="auto" 사용 시 모델이 여러 GPU에 걸쳐 있을 수 있으므로, 첫 번째 레이어의 장치를 따라갑니다.
            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
            
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    temperature=0.7,
                    top_p=0.9,
                    do_sample=True,
                    repetition_penalty=1.05,
                    eos_token_id=self.tokenizer.eos_token_id,
                    pad_token_id=self.tokenizer.eos_token_id
                )
            
            generated_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            # 입력 프롬프트 이후의 생성된 텍스트만 반환
            return generated_text[len(prompt):].strip()
            
        except Exception as e:
            print(f"[ERROR] StoryAgent 생성 오류: {e}")
            return "시스템: 대화 생성 중 오류가 발생했습니다."

    def generate_diary(self, messages, fish_level=3, max_new_tokens=400) -> str:
        """
        하루의 대화 로그를 바탕으로 일기(스토리 요약)를 작성합니다.
        """
        # GPU Proxy 모드: AWS EC2 GPU 서버에 위임
        if settings.USE_GPU_PROXY:
            try:
                server_url = settings.GPU_SERVER_URL.rstrip("/")
                with httpx.Client(timeout=settings.GPU_PROXY_TIMEOUT) as client:
                    response = client.post(
                        f"{server_url}/infer/story/diary",
                        json={
                            "messages": str(messages),
                            "fish_level": fish_level,
                            "max_new_tokens": max_new_tokens
                        }
                    )
                    response.raise_for_status()
                    return response.json()["text"]
            except Exception as e:
                print(f"⚠️ [StoryAgent] GPU Proxy Diary 오류: {e}")
                return "시스템: GPU 서버에 연결할 수 없습니다."

        if not self.model or not self.tokenizer:
            return "시스템: 모델이 로드되지 않아 일기를 작성할 수 없습니다."

        system_prompt = (
            "너는 텍스트 기반 잠입수사 게임 Project: UMI_PROTOCOL의 스토리 에이전트다. "
            "입력은 하루의 대화 로그(messages)이며, 이를 바탕으로 '일기'만 작성한다. "
            "톤은 어둡고 불안하며 잠입수사 기록처럼 건조해야 한다. "
            "밝은/훈훈/희망적 표현 금지. "
            "fish_level이 높을수록 감각 왜곡(어안렌즈, 비린내, 청각 왜곡 등)을 더 반영한다. "
            "출력은 JSON이 아니라 '일기 본문 텍스트만' 출력한다."
        )

        user_prompt = (
            f"[fish_level={fish_level}]\n"
            "아래 messages 로그만 근거로 일기를 작성해. 새 사실 창작 금지.\n"
            "조건: 7~10문장, 줄바꿈 없이 한 덩어리로.\n\n"
            f"{messages}"
        )

        chat = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            # apply_chat_template을 사용하여 프롬프트 생성
            prompt = self.tokenizer.apply_chat_template(chat, tokenize=False, add_generation_prompt=True)
            # generate 메서드 재사용 (prompt가 이미 완성된 형태이므로 그대로 전달)
            return self.generate(prompt, max_new_tokens)
        except Exception as e:
            print(f"[ERROR] StoryAgent 일기 생성 오류: {e}")
            return "시스템: 일기 생성 중 오류가 발생했습니다."

# 싱글톤 인스턴스 생성
story_agent = StoryAgent()