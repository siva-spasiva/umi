"""
NPC 대화 생성 시스템 (프로덕션)
- UmiJudger: 의도/감정 분석 (분류 모델)
- DialogueGenerator: 실제 대화 생성 (Gemma-2 또는 다른 LLM)
- RAG: 세계관 지식 검색
- 상태 관리: friendly, faith, fish_level
"""

import os
import re
import json
import torch
import torch.nn as nn
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Tuple
from transformers import AutoTokenizer, AutoModel, AutoModelForCausalLM

# ============================================================
# 1. 상태 관리
# ============================================================

@dataclass
class NPCState:
    """NPC 관계 상태"""
    friendly: int = 50  # 0~100
    faith: int = 50     # 0~100
    fish_level: int = 0 # 물고기 변이 단계
    
    def apply_delta(self, friendly_delta: int, faith_delta: int):
        """스탯 변화 적용"""
        self.friendly = max(0, min(100, self.friendly + friendly_delta))
        self.faith = max(0, min(100, self.faith + faith_delta))
    
    def to_dict(self) -> Dict[str, int]:
        return asdict(self)


def get_relationship_bucket(friendly: int) -> str:
    """
    관계도에 따른 페르소나 선택 (4단계)
    - bad: 0-19 (적대적)
    - normal: 20-45 (중립)
    - good: 46-75 (호의적)
    - perfect: 76-100 (완전 신뢰)
    """
    if friendly <= 19:
        return "bad"
    elif friendly <= 45:
        return "normal"
    elif friendly <= 75:
        return "good"
    return "perfect"


# ============================================================
# 2. UmiJudger - 의도/감정 분석 모델
# ============================================================

VALID_TAGS = [
    "MAINTAIN_FAITH", "SHAKE_FAITH", "PROTECT_DOCTRINE",
    "PROTECT_SECRET", "INCREASE_SUSPICION", "REDUCE_SUSPICION",
    "DEFLECT", "GASLIGHT", "TEST_BOUNDARY",
    "BUILD_TRUST", "WITHDRAW_TRUST", "OPPORTUNISTIC"
]


class UmiJudger(nn.Module):
    """대화 의도 및 감정 변화 예측 모델"""
    
    def __init__(self, model_name: str, num_tags: int = 12):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(model_name)
        hidden_size = self.encoder.config.hidden_size
        self.dropout = nn.Dropout(0.1)
        self.tag_head = nn.Linear(hidden_size, num_tags)
        self.friendly_head = nn.Linear(hidden_size, 11)  # -5 ~ +5
        self.faith_head = nn.Linear(hidden_size, 11)     # -5 ~ +5
    
    def forward(self, input_ids, attention_mask):
        outputs = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        cls_output = outputs.last_hidden_state[:, 0, :]
        cls_output = self.dropout(cls_output)
        return (
            self.tag_head(cls_output),
            self.friendly_head(cls_output),
            self.faith_head(cls_output)
        )


class IntentAnalyzer:
    """의도 분석 엔진 (UmiJudger 래퍼) — v2: per-tag threshold + top-k fallback"""
    
    def __init__(
        self, 
        encoder_model: str = "monologg/koelectra-base-v3-discriminator",
        checkpoint_path: str = None,
        max_length: int = 256,
        tag_k: int = 3,
        tag_min_p: float = 0.15,
        threshold_json_path: Optional[str] = None,
        device: Optional[str] = None
    ):
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.max_length = max_length
        self.tag_k = int(tag_k)
        self.tag_min_p = float(tag_min_p)
        
        # 토크나이저 로드
        self.tokenizer = AutoTokenizer.from_pretrained(encoder_model)
        
        # 모델 로드
        self.model = UmiJudger(encoder_model, num_tags=len(VALID_TAGS)).to(self.device)
        
        # 체크포인트 로드
        if checkpoint_path and os.path.exists(checkpoint_path):
            print(f"[IntentAnalyzer] Loading checkpoint: {checkpoint_path}")
            state_dict = torch.load(checkpoint_path, map_location=self.device)
            self.model.load_state_dict(state_dict)
        else:
            print(f"[IntentAnalyzer] No checkpoint loaded. Using base model.")
        
        self.model.eval()
        
        # 태그별 threshold 로드 (thresholds_standard.json)
        self.tag_thresholds: Dict[str, float] = {t: 0.5 for t in VALID_TAGS}  # fallback
        if threshold_json_path and os.path.exists(threshold_json_path):
            with open(threshold_json_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            # JSON 형식: {"tags": [...], "thresholds": [...]} 또는 {"TAG_NAME": value}
            if "tags" in loaded and "thresholds" in loaded:
                for tag_name, thresh_val in zip(loaded["tags"], loaded["thresholds"]):
                    if tag_name in self.tag_thresholds:
                        self.tag_thresholds[tag_name] = float(thresh_val)
            else:
                for t in VALID_TAGS:
                    if t in loaded:
                        self.tag_thresholds[t] = float(loaded[t])
            print(f"[IntentAnalyzer] Loaded per-tag thresholds: {threshold_json_path}")
        else:
            print(f"[IntentAnalyzer] No threshold JSON found. Using fallback=0.5 for all tags.")
    
    @torch.no_grad()
    def analyze(self, text: str) -> Dict[str, Any]:
        """
        텍스트 의도 분석 (v2: per-tag threshold + top-k fallback)
        
        Returns:
            {
                "reason_tags": List[str],
                "friendly_delta": int,
                "faith_delta": int,
                "tag_probs": Dict[str, float]
            }
        """
        # 토크나이징
        encoding = self.tokenizer(
            text,
            padding="max_length",
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt"
        )
        
        # token_type_ids 제거 (일부 모델은 사용 안 함)
        if "token_type_ids" in encoding:
            encoding.pop("token_type_ids")
        
        encoding = {k: v.to(self.device) for k, v in encoding.items()}
        
        # 예측
        tag_logits, friendly_logits, faith_logits = self.model(**encoding)
        
        # 태그 확률 계산
        probs = torch.sigmoid(tag_logits)[0]
        tag_probs = {VALID_TAGS[i]: float(probs[i]) for i in range(len(VALID_TAGS))}
        
        # 1) per-tag threshold로 먼저 선택
        picked = [t for t in VALID_TAGS if tag_probs[t] >= self.tag_thresholds.get(t, 0.5)]
        
        # 2) 아무것도 안 걸리면 top-k fallback
        if not picked:
            ranked = sorted(tag_probs.items(), key=lambda x: -x[1])
            picked = [t for t, p in ranked[:max(1, self.tag_k)] if p >= self.tag_min_p]
            if not picked:
                picked = [ranked[0][0]]
        
        # 3) 너무 많이 걸리면 상위 k개로 제한
        if len(picked) > self.tag_k:
            picked = sorted(picked, key=lambda t: -tag_probs[t])[:self.tag_k]
        
        # 감정 변화 예측 (-5 ~ +5)
        friendly_delta = max(-5, min(5, int(torch.argmax(friendly_logits, dim=1).item()) - 5))
        faith_delta = max(-5, min(5, int(torch.argmax(faith_logits, dim=1).item()) - 5))
        
        print(f"\n[DEBUG] 의도 분석 결과:")
        print(f"  선택된 태그: {picked}")
        print(f"  태그 확률 (상위 5개): {sorted(tag_probs.items(), key=lambda x: -x[1])[:5]}")
        print(f"  감정 변화: friendly={friendly_delta:+d}, faith={faith_delta:+d}")
        
        return {
            "reason_tags": picked,
            "friendly_delta": friendly_delta,
            "faith_delta": faith_delta,
            "tag_probs": tag_probs
        }


# ============================================================
# 3. DialogueGenerator - 대화 생성 엔진
# ============================================================

class DialogueGenerator:
    """
    대화 생성 엔진 (Gemma-2 기반)
    - 4bit 양자화 우선 시도, 실패 시 fp16 fallback
    """
    
    def __init__(
        self,
        model_name: str = "google/gemma-2-2b-it",
        hf_token: Optional[str] = None,
        use_4bit: bool = True
    ):
        self.model_name = model_name
        self.hf_token = hf_token
        
        # 토크나이저 로드
        print(f"[DialogueGenerator] Loading tokenizer: {model_name}")
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name, 
            token=hf_token,
            use_fast=True
        )
        
        # system role 지원 확인
        self._supports_system = self._check_system_support()
        
        # 모델 로드
        self.model = self._load_model(use_4bit)
        print(f"[DialogueGenerator] Model ready on {self.model.device}")
    
    def _check_system_support(self) -> bool:
        """모델이 system role을 지원하는지 확인"""
        try:
            if hasattr(self.tokenizer, "apply_chat_template"):
                self.tokenizer.apply_chat_template(
                    [
                        {"role": "system", "content": "test"},
                        {"role": "user", "content": "hi"}
                    ],
                    tokenize=False,
                    add_generation_prompt=True
                )
                return True
        except Exception:
            return False
        return False
    
    def _load_model(self, use_4bit: bool):
        """모델 로드 (4bit 시도 후 fp16 fallback)"""
        kwargs = {
            "token": self.hf_token,
            "device_map": "auto"
        }
        
        if torch.cuda.is_available():
            kwargs["torch_dtype"] = torch.float16
        
        # 1) 4bit 양자화 시도
        if use_4bit:
            try:
                from transformers import BitsAndBytesConfig
                
                bnb_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4"
                )
                kwargs["quantization_config"] = bnb_config
                
                print("[DialogueGenerator] Trying 4bit quantization...")
                model = AutoModelForCausalLM.from_pretrained(self.model_name, **kwargs)
                model.eval()
                print("[DialogueGenerator] ✅ 4bit load successful")
                return model
                
            except Exception as e:
                print(f"[DialogueGenerator] ⚠️ 4bit failed, fallback to fp16: {e}")
        
        # 2) fp16 로드
        kwargs.pop("quantization_config", None)
        model = AutoModelForCausalLM.from_pretrained(self.model_name, **kwargs)
        model.eval()
        print("[DialogueGenerator] ✅ fp16 load successful")
        return model
    
    def _build_messages(self, system: str, user: str) -> List[Dict[str, str]]:
        """메시지 구성 (system role 지원 여부에 따라)"""
        if self._supports_system:
            return [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ]
        else:
            # system role 미지원 시 user message에 포함
            merged = f"[SYSTEM]\n{system}\n\n[USER]\n{user}"
            return [{"role": "user", "content": merged}]
    
    @torch.no_grad()
    def generate(
        self,
        system_prompt: str,
        user_message: str,
        max_new_tokens: int = 160,
        do_sample: bool = False,
        temperature: float = 0.8,
        top_p: float = 0.9,
        repetition_penalty: float = 1.05
    ) -> str:
        """
        대화 생성
        
        Args:
            system_prompt: 시스템 프롬프트 (페르소나 + 컨트롤 시그널)
            user_message: 사용자 메시지
            max_new_tokens: 생성할 최대 토큰 수
            do_sample: 샘플링 사용 여부
            temperature: 샘플링 온도
            top_p: nucleus sampling
            repetition_penalty: 반복 패널티
            
        Returns:
            생성된 대화 텍스트
        """
        messages = self._build_messages(system_prompt, user_message)
        
        # chat template 적용
        if hasattr(self.tokenizer, "apply_chat_template"):
            template_output = self.tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt"
            )
            
            if isinstance(template_output, torch.Tensor):
                model_inputs = {"input_ids": template_output.to(self.model.device)}
            else:
                model_inputs = {k: v.to(self.model.device) for k, v in template_output.items()}
            
            input_ids = model_inputs["input_ids"]
            prompt_length = input_ids.shape[-1]
            
            # 생성
            gen_kwargs = {
                **model_inputs,
                "max_new_tokens": max_new_tokens,
                "do_sample": do_sample,
                "repetition_penalty": repetition_penalty,
                "use_cache": True
            }
            
            if do_sample:
                gen_kwargs.update({
                    "temperature": temperature,
                    "top_p": top_p
                })
            
            outputs = self.model.generate(**gen_kwargs)
            generated_ids = outputs[0][prompt_length:]
            return self.tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
        
        else:
            # fallback: 단순 텍스트 생성
            prompt = f"{system_prompt}\n\n[플레이어]\n{user_message}\n\n[NPC]\n"
            encoding = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
            outputs = self.model.generate(
                **encoding,
                max_new_tokens=max_new_tokens,
                do_sample=do_sample
            )
            text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            return text.split("[NPC]")[-1].strip()


# ============================================================
# 4. 유틸리티 함수
# ============================================================

def sanitize_npc_response(text: str) -> str:
    """
    NPC 응답에서 불필요한 요소 제거
    - 코드 블록 (```)
    - 마크다운 헤더 (###)
    - [NPC], [플레이어] 등의 태그
    """
    text = (text or "").strip()
    
    # 코드 블록 제거
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    
    # Stop Tokens / Hallucination Cutting
    for stop_word in ["<end_of_turn>", "<start_of_turn>", "<eos>", "User:", "Model:", "user:", "model:"]:
        if stop_word in text:
            text = text.split(stop_word)[0]
            
    # Remove Leaked Control Signals (e.g., (DEFLECT/GASLIGHT))
    text = re.sub(r"\([A-Z_]+(?:/[A-Z_]+)*\)", "", text)
    
    # Remove Markdown headers/bold
    text = re.sub(r"^###.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*.*?\*\*", "", text) # Remove bold wrapping if any
    
    # Remove Tags
    text = re.sub(r"\[(NPC|Player|User|System|Model|CheongGalchi)\]", "", text, flags=re.IGNORECASE)
    
    # 선택지 패턴 제거
    text = re.sub(r"^\d+\.\s+.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[가-힣]\)\s+.*$", "", text, flags=re.MULTILINE)
    
    # 이모지 제거
    text = re.sub(
        r"[\U0001F600-\U0001F64F"   # Emoticons
        r"\U0001F300-\U0001F5FF"     # Misc Symbols & Pictographs
        r"\U0001F680-\U0001F6FF"     # Transport & Map
        r"\U0001F1E0-\U0001F1FF"     # Flags
        r"\U00002702-\U000027B0"     # Dingbats
        r"\U0000FE00-\U0000FE0F"     # Variation Selectors
        r"\U0001F900-\U0001F9FF"     # Supplemental Symbols
        r"\U0001FA00-\U0001FA6F"     # Chess Symbols
        r"\U0001FA70-\U0001FAFF"     # Symbols Extended-A
        r"\U00002600-\U000026FF"     # Misc Symbols
        r"\U0000200D"                # Zero Width Joiner
        r"\U00002B50\U00002B55"      # Stars
        r"]+", "", text
    )

    # [CRITICAL] Foreign Language Filter (Chinese Hallucination Fix)
    # If the text contains Chinese characters (common Gemma issue), cut off the text OR remove them.
    # Pattern: Korean sentence... followed by Chinese text.
    if re.search(r"[\u4e00-\u9fff]", text):
        # Strategy: Find the first Chinese character and cut off everything after it (assuming it's hallucination start)
        match = re.search(r"[\u4e00-\u9fff]", text)
        if match:
            print(f"[Sanitize] Detected Chinese characters. Truncating response at index {match.start()}.")
            text = text[:match.start()].strip()
            
    # 연속된 줄바꿈 정리
    text = re.sub(r"\n{3,}", "\n\n", text)
    
    return text.strip()


def format_control_signal(
    tags: List[str],
    friendly_delta: int,
    faith_delta: int
) -> str:
    """
    컨트롤 시그널 포맷팅 (한국어)
    - 분석 결과를 LLM이 이해할 수 있는 형태로 변환
    """
    tag_str = ", ".join(tags) if tags else "NONE"
    
    signal = f"""[CONTROL_SIGNAL]
REASON_TAGS={tag_str}
PREDICTED_DELTA friendly={friendly_delta:+d}, faith={faith_delta:+d}

GUIDANCE:
- If WITHDRAW_TRUST: Strengthen suspicion/distancing/counter-questioning.
- If BUILD_TRUST: Keep possibility of trade proposal/cooperation open.
- If DEFLECT/GASLIGHT/TEST_BOUNDARY/INCREASE_SUSPICION: Avoid direct answers + Test the other.
- If PROTECT_SECRET/PROTECT_DOCTRINE: Hide core info and provide only hints.
"""
    return signal.strip()


if __name__ == "__main__":
    # 간단한 테스트
    print("=== NPC Dialogue System Test ===")
    
    # 1. 의도 분석기 초기화
    analyzer = IntentAnalyzer(
        checkpoint_path="./NPC_model/best_model.pt"  # 실제 경로로 수정
    )
    
    # 2. 테스트 분석
    test_text = "SPEAKER:user\nTARGET:umi\nFRIENDLY:50\nFAITH:50\n[msg] 안녕? 오늘 기분 어때?"
    result = analyzer.analyze(test_text)
    
    print("\n분석 결과:")
    print(f"  태그: {result['reason_tags']}")
    print(f"  호감도 변화: {result['friendly_delta']:+d}")
    print(f"  신뢰도 변화: {result['faith_delta']:+d}")
