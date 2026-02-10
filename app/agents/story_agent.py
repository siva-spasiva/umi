import os
import torch
import httpx
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import PeftModel
from app.core.config import settings

try:
    from mlx_lm import load as mlx_load, generate as mlx_generate
    HAS_MLX = True
except ImportError:
    HAS_MLX = False

class StoryAgent:
    """
    Story Agent: LLM을 사용하여 스토리 진행, 대화 생성, 요약 등을 수행합니다.
    """
    def __init__(self):
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
        
        # [Ollama 모드] 로컬 개발 시 Ollama 서버 사용 (USE_OLLAMA=true)
        self.use_ollama = settings.USE_OLLAMA
        self.ollama_url = settings.OLLAMA_URL or "http://localhost:11434/api/generate"
        self.ollama_model = settings.OLLAMA_MODEL or "llama3"

        # [MLX 모드] Apple Silicon 가속 사용
        # 주의: MLX는 .pt 파일을 직접 읽지 못하므로, 변환된 모델이 있을 때만 .env에서 USE_MLX=true로 설정하세요.
        self.use_mlx = settings.USE_MLX
        if self.use_mlx and not HAS_MLX:
            print("⚠️ [StoryAgent] USE_MLX is True but mlx-lm is not installed. Fallback to PyTorch.")
            self.use_mlx = False

        if torch.cuda.is_available():
            self.device = "cuda"
        elif torch.backends.mps.is_available():
            self.device = "mps"
        else:
            self.device = "cpu"
            
        self.model = None
        self.tokenizer = None
        
        if self.use_ollama:
            print(f"🐙 [StoryAgent] Ollama Mode Activated - URL: {self.ollama_url}, Model: {self.ollama_model}")
            # [경고] Ollama 모드에서는 로컬 모델 경로가 무시됨을 알림
            if self.adapter_path:
                print(f"⚠️ [WARN] Ollama 모드 사용 중: 로컬 모델 경로 '{self.adapter_path}'는 무시됩니다.")
                print(f"          Ollama 서버에 등록된 '{self.ollama_model}' 모델을 사용합니다.")
        elif self.use_mlx:
            print(f"🍎 [StoryAgent] MLX Mode Activated")
            self._load_mlx_model()
        else:
            # Ollama 모드가 아니면 실제 모델 로드 시도 (GPU/CPU)
            self._load_model()

    def _load_mlx_model(self):
        """MLX를 사용하여 모델을 로드합니다."""
        try:
            path_to_load = self.adapter_path if (self.adapter_path and os.path.exists(self.adapter_path)) else self.base_model_id
            
            if os.path.isdir(path_to_load) and "best_model.pt" in os.listdir(path_to_load):
                print(f"⚠️ [StoryAgent] MLX 모드 경고: '{path_to_load}' 폴더에 'best_model.pt'가 감지되었습니다.")
                print("          MLX 라이브러리는 PyTorch(.pt) 가중치를 직접 로드하지 못할 수 있습니다.")
                print("          모델을 MLX 포맷으로 변환하거나, PyTorch 모드(USE_MLX=false)를 사용하세요.")

            print(f"🔄 [StoryAgent] Loading MLX Model from: {path_to_load}...")
            self.model, self.tokenizer = mlx_load(path_to_load)
            print(f"✅ [StoryAgent] MLX Model Loaded")
        except Exception as e:
            print(f"⚠️ [StoryAgent] MLX 모델 로드 실패: {e}")

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
        # 1. Ollama 사용 (로컬 테스트)
        if self.use_ollama:
            try:
                payload = {
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": max_new_tokens}
                }
                # 타임아웃을 넉넉하게 설정 (로컬 LLM 속도 고려)
                with httpx.Client(timeout=60.0) as client:
                    response = client.post(self.ollama_url, json=payload)
                    
                    # [에러 디버깅] 404 등 에러 발생 시 상세 메시지 출력
                    if response.status_code != 200:
                        print(f"⚠️ [StoryAgent] Ollama Error ({response.status_code}): {response.text}")

                    response.raise_for_status()
                    res_json = response.json()
                    
                    # [검증용 로그] Ollama 처리 속도 출력 (GPU 사용 시 매우 빠름)
                    total_ns = res_json.get("total_duration", 0)
                    eval_count = res_json.get("eval_count", 0)
                    print(f"🐙 [StoryAgent/Ollama] 생성 완료: {eval_count} tokens (소요시간: {total_ns/1e9:.2f}s)")
                    
                    return res_json.get("response", "")
            except Exception as e:
                print(f"[ERROR] Ollama 생성 오류: {e}")
                return "시스템: Ollama 서버와 통신할 수 없습니다."

        # 2. MLX 사용
        if self.use_mlx:
            try:
                response = mlx_generate(self.model, self.tokenizer, prompt=prompt, max_tokens=max_new_tokens, verbose=False, temp=0.7)
                return response.strip()
            except Exception as e:
                print(f"[ERROR] MLX 생성 오류: {e}")
                return "시스템: 대화 생성 중 오류가 발생했습니다."

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
        Colab의 make_diary_from_messages 로직을 이식했습니다.
        """
        if self.use_ollama:
            # Ollama 사용 시 간단히 프롬프트 결합하여 요청
            full_prompt = (
                f"System: 너는 텍스트 기반 잠입수사 게임 Project: UMI_PROTOCOL의 스토리 에이전트다. "
                f"입력은 하루의 대화 로그(messages)이며, 이를 바탕으로 '일기'만 작성한다.\n"
                f"User: [fish_level={fish_level}]\n{messages}\nAssistant:"
            )
            return self.generate(full_prompt, max_new_tokens)

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