import os
import torch
import httpx
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from app.core.config import settings

# MLX 라이브러리 로드 시도 (Apple Silicon 환경이 아닐 경우를 대비)
try:
    from mlx_lm import load as mlx_load, generate as mlx_generate
    HAS_MLX = True
except ImportError:
    HAS_MLX = False

class NpcAgent:
    """
    NPC Agent: NPC 공통 모델을 사용하여 페르소나 기반 대화 및 상태 변화를 예측합니다.
    """
    def __init__(self):
        # 기본 베이스 모델 (Gemma 2 9B IT)
        self.base_model_id = "google/gemma-2-9b-it"
        
        # [경로 자동 보정]
        # app/agents/NPC_model 폴더를 우선적으로 찾습니다.
        base_dir = os.path.dirname(os.path.abspath(__file__))
        local_model_path = os.path.join(base_dir, "NPC_model")

        # 어댑터 경로 설정 (우선순위: 환경변수 > 로컬 폴더 > None)
        if settings.NPC_MODEL_PATH and os.path.exists(settings.NPC_MODEL_PATH):
            self.adapter_path = settings.NPC_MODEL_PATH
        elif os.path.exists(local_model_path):
            print(f"📂 [NpcAgent] 로컬 모델 폴더 감지: {local_model_path}")
            self.adapter_path = local_model_path
        else:
            self.adapter_path = settings.NPC_MODEL_PATH

        # [Ollama 모드]
        self.use_ollama = settings.USE_OLLAMA
        self.ollama_url = settings.OLLAMA_URL or "http://localhost:11434/api/generate"
        self.ollama_model = settings.OLLAMA_MODEL or "llama3"

        # [MLX 모드] Apple Silicon 가속 사용
        # 주의: MLX는 .pt 파일을 직접 읽지 못하므로, 변환된 모델이 있을 때만 .env에서 USE_MLX=true로 설정하세요.
        self.use_mlx = settings.USE_MLX
        if self.use_mlx and not HAS_MLX:
            print("⚠️ [NpcAgent] USE_MLX is True but mlx-lm is not installed. Fallback to PyTorch.")
            self.use_mlx = False

        if torch.cuda.is_available():
            self.device = "cuda"
        elif torch.backends.mps.is_available():
            self.device = "mps"
        else:
            self.device = "cpu"
            
        self.model = None
        self.tokenizer = None
        
        print(f"🔍 [NpcAgent] Config Check: USE_OLLAMA={self.use_ollama}")

        if self.use_ollama:
            print(f"🐙 [NpcAgent] Ollama Mode Activated - URL: {self.ollama_url}, Model: {self.ollama_model}")
            # [경고] Ollama 모드에서는 로컬 모델 경로가 무시됨을 알림
            if self.adapter_path:
                print(f"⚠️ [WARN] Ollama 모드 사용 중: 로컬 모델 경로 '{self.adapter_path}'는 무시됩니다.")
                print(f"          Ollama 서버에 등록된 '{self.ollama_model}' 모델을 사용합니다.")
        elif self.use_mlx:
            print(f"🍎 [NpcAgent] MLX Mode Activated")
            self._load_mlx_model()
        else:
            self._load_model()

    def _load_mlx_model(self):
        """MLX를 사용하여 모델을 로드합니다."""
        try:
            # adapter_path가 있으면 그것을 우선 사용, 없으면 base_model_id 사용
            # 주의: MLX는 PyTorch LoRA 어댑터(.pt/.bin)를 직접 로드하지 못할 수 있으며,
            # MLX 포맷으로 변환된 모델이나 병합된 모델 경로를 지정해야 할 수 있습니다.
            path_to_load = self.adapter_path if (self.adapter_path and os.path.exists(self.adapter_path)) else self.base_model_id
            
            if os.path.isdir(path_to_load) and "best_model.pt" in os.listdir(path_to_load):
                print(f"⚠️ [NpcAgent] MLX 모드 경고: '{path_to_load}' 폴더에 'best_model.pt'가 감지되었습니다.")
                print("          MLX 라이브러리는 PyTorch(.pt) 가중치를 직접 로드하지 못할 수 있습니다.")
                print("          모델을 MLX 포맷으로 변환하거나, PyTorch 모드(USE_MLX=false)를 사용하세요.")

            print(f"🔄 [NpcAgent] Loading MLX Model from: {path_to_load}...")
            self.model, self.tokenizer = mlx_load(path_to_load)
            print(f"✅ [NpcAgent] MLX Model Loaded")
        except Exception as e:
            print(f"⚠️ [NpcAgent] MLX 모델 로드 실패: {e}")

    def _load_model(self):
        """서버 시작 시 NPC 모델(LLM)을 메모리에 로드합니다."""
        try:
            # 토크나이저는 어댑터 경로에 있으면 거기서, 없으면 베이스 모델에서 로드
            tokenizer_path = self.adapter_path if (self.adapter_path and os.path.exists(self.adapter_path)) else self.base_model_id
            print(f"🔄 [NpcAgent] Loading Tokenizer: {tokenizer_path}...")
            
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
            
            print(f"🔄 [NpcAgent] Loading Base Model: {self.base_model_id}...")
            
            # from_pretrained 인자 설정
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
                best_model_path = os.path.join(self.adapter_path, "best_model.pt")
                if os.path.exists(best_model_path):
                    print(f"🔄 [NpcAgent] Loading Custom Model Weights from: {best_model_path}")
                    state_dict = torch.load(best_model_path, map_location=self.device)
                    
                    # 전체 모델 가중치로 가정하고 로드 (strict=False: 일부 키 불일치 허용)
                    base_model.load_state_dict(state_dict, strict=False)
                    print(f"✅ [NpcAgent] Custom Weights (best_model.pt) Loaded on {self.device}")
                else:
                    print(f"⚠️ [NpcAgent] 'best_model.pt' not found. Using Base Model.")
            
            self.model = base_model
            print(f"✅ [NpcAgent] Model Ready on {self.device}")

            self.model.eval()
        except Exception as e:
            print(f"⚠️ [NpcAgent] 모델 로드 실패: {e}")
            if self.adapter_path and os.path.exists(self.adapter_path):
                # .pt 파일이 있는지 확인하여 힌트 제공
                files = os.listdir(self.adapter_path)
                pt_files = [f for f in files if f.endswith('.pt')]
                if pt_files and not any(f.endswith(('.bin', '.safetensors')) for f in files):
                    print(f"   👉 (힌트) 폴더에 '{pt_files[0]}' 파일이 감지되었습니다.")
                    print(f"       PeftModel은 'adapter_model.bin' 이름을 기대합니다. 해당 파일의 이름을 변경해주세요.")

            if self.adapter_path and os.path.sep in self.adapter_path:
                print(f"   👉 (힌트) 로컬 경로 '{self.adapter_path}'가 정확한지 확인하세요. (현재 실행 위치: {os.getcwd()})")

    def generate(self, prompt: str, max_new_tokens: int = 256) -> str:
        """프롬프트를 입력받아 텍스트를 생성합니다."""
        # 1. Ollama 사용
        if self.use_ollama:
            try:
                payload = {
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": max_new_tokens}
                }
                with httpx.Client(timeout=60.0) as client:
                    response = client.post(self.ollama_url, json=payload)
                    
                    # [에러 디버깅] 404 등 에러 발생 시 상세 메시지 출력 (모델 미설치 확인용)
                    if response.status_code != 200:
                        print(f"⚠️ [NpcAgent] Ollama Error ({response.status_code}): {response.text}")

                    response.raise_for_status()
                    res_json = response.json()
                    
                    # [검증용 로그] Ollama 처리 속도 출력
                    total_ns = res_json.get("total_duration", 0)
                    eval_count = res_json.get("eval_count", 0)
                    print(f"🐙 [NpcAgent/Ollama] 생성 완료: {eval_count} tokens (소요시간: {total_ns/1e9:.2f}s)")
                    
                    return res_json.get("response", "")
            except Exception as e:
                print(f"[ERROR] Ollama 생성 오류: {e}")
                return "시스템: Ollama 서버와 통신할 수 없습니다."

        # 2. MLX 사용
        if self.use_mlx:
            print(f"🚀 [NpcAgent] MLX 생성 시작... (Prompt 길이: {len(prompt)})")
            try:
                # mlx_generate는 생성된 텍스트만 반환합니다.
                response = mlx_generate(self.model, self.tokenizer, prompt=prompt, max_tokens=max_new_tokens, verbose=False, temp=0.7)
                return response.strip()
            except Exception as e:
                print(f"[ERROR] MLX 생성 오류: {e}")
                return "시스템: 대화 생성 중 오류가 발생했습니다."

        print(f"🚀 [NpcAgent] 생성 시작... (Device: {self.device}, Prompt 길이: {len(prompt)})")
        if not self.model or not self.tokenizer:
            return "시스템: 모델이 로드되지 않아 응답할 수 없습니다."

        try:
            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
            
            # Gemma 모델은 token_type_ids 인자를 받지 않으므로 제거해야 합니다.
            if "token_type_ids" in inputs:
                del inputs["token_type_ids"]
            
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
            result = generated_text[len(prompt):].strip()
            print(f"✅ [NpcAgent] 생성 완료: {result[:50]}...")
            return result
            
        except Exception as e:
            print(f"[ERROR] NpcAgent 생성 오류: {e}")
            return "시스템: 대화 생성 중 오류가 발생했습니다."

# 싱글톤 인스턴스 생성
npc_agent = NpcAgent()