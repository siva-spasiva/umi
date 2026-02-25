import os
import torch
import httpx
import json
from datetime import datetime
from typing import Any, Dict, List
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import PeftModel
from app.core.config import settings

class StoryAgent:
    """
    Story Agent: LLM을 사용하여 스토리 진행, 대화 생성, 요약 등을 수행합니다.
    """
    def __init__(self):
        # Mock 모드: 모델 로드 건너뛰기
        if settings.MOCK_MODE:
            print("[StoryAgent] Mock mode — skipping model loading")
            self.model = None
            self.tokenizer = None
            return

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

    async def generate(self, prompt: str, max_new_tokens: int = 256, temperature: float = 0.7, top_p: float = 0.9) -> str:
        """프롬프트를 입력받아 텍스트를 생성합니다 (비동기)."""
        import json as _json

        # Mock 모드
        if settings.MOCK_MODE:
            # EPILOGUE 모드 감지
            if '"mode": "EPILOGUE"' in prompt or '"mode":"EPILOGUE"' in prompt:
                return _json.dumps({
                    "title": "드러난 진실",
                    "text": "5일간의 조사 끝에, UMI 교단의 실체가 드러났다. 교단은 이미 마을 깊숙이 뿌리를 내리고 있었고, 그 중심에는 예상치 못한 인물이 있었다.",
                    "ending_type": "exposed",
                    "reason": "체계적인 증거 수집과 NPC들의 신뢰를 얻어 핵심 정보에 접근할 수 있었다."
                }, ensure_ascii=False)
            # DIARY 모드 (기본)
            return _json.dumps({
                "diary": {"title": "수상한 움직임", "text": "오늘 하루도 기묘한 일들이 이어졌다.", "tone": "긴장감"},
                "summary_bullets": ["마을 주민과의 대화에서 단서 발견", "의문의 물건 획득"],
                "key_conversations": [],
                "items": [],
                "clues": [{"info": "교단의 의식 장소에 대한 힌트", "importance": "high"}],
                "troll_level_analysis": {"delta_total": 0, "top_causes": []},
                "consistency_check": {"contradictions_found": [], "missing_info": []},
                "ending": {"status": "continue", "ending_type": "null", "reason": "", "required_next_step": ""},
                "flags_for_next_day": [],
                "safety": {"hallucination_risk": "low", "spoiler_blocked": True}
            }, ensure_ascii=False)

        # GPU Proxy 모드: AWS EC2 GPU 서버에 위임
        if settings.USE_GPU_PROXY:
            try:
                server_url = settings.GPU_SERVER_URL.rstrip("/")
                async with httpx.AsyncClient(timeout=settings.GPU_PROXY_TIMEOUT) as client:
                    response = await client.post(
                        f"{server_url}/infer/story",
                        json={
                            "prompt": prompt, 
                            "max_new_tokens": max_new_tokens,
                            "temperature": temperature,
                            "top_p": top_p
                        }
                    )
                    response.raise_for_status()
                    return response.json()["text"]
            except Exception as e:
                print(f"⚠️ [StoryAgent] GPU Proxy 오류: {e}")
                return "시스템: GPU 서버에 연결할 수 없습니다."

        try:
            # 로컬 생성 (비동기 실행을 위해 스레드 풀 사용)
            def _sync_generate():
                inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
                with torch.no_grad():
                    outputs = self.model.generate(
                        **inputs,
                        max_new_tokens=max_new_tokens,
                        temperature=temperature,
                        top_p=top_p,
                        do_sample=True if temperature > 0 else False,
                        repetition_penalty=1.05,
                        eos_token_id=self.tokenizer.eos_token_id,
                        pad_token_id=self.tokenizer.eos_token_id
                    )
                generated_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
                return generated_text[len(prompt):].strip()

            return await asyncio.to_thread(_sync_generate)
            
        except Exception as e:
            print(f"[ERROR] StoryAgent 생성 오류: {e}")
            return "시스템: 대화 생성 중 오류가 발생했습니다."

    def generate_diary(self, messages, fish_level=3, max_new_tokens=400) -> str:
        """
        [Legacy] 하루의 대화 로그를 바탕으로 일기를 작성합니다 (동기 호환용).
        기존 LLMEngine 등에서 호출할 수 있으므로 유지하되, 내부적으로는 asyncio.run 등 주의 필요.
        """
        # [TODO] LLMEngine을 async로 전환하는 것이 좋지만, 일단 이 메서드는 async를 호출하도록 구현
        try:
            import asyncio
            return asyncio.run(self.generate(messages, max_new_tokens))
        except Exception:
            return "일기 생성 실패"

    async def _get_system_prompt(self) -> str:
        """MongoDB에서 스토리 에이전트 전용 시스템 프롬프트를 가져옵니다."""
        from app.core.database import db
        doc = await db["agent_prompts"].find_one({"_id": "story_agent"})
        if doc and "system" in doc:
            return doc["system"]
        
        # Fallback (DB에 없는 경우 기존 코드 기반 프롬프트)
        return (
            "You are the Story Agent for the infiltration investigation game \"Project: UMI\".\n"
            "Your role is record keeping only.\n"
            "Output JSON ONLY."
        )

    def _required_keys_for_mode(self, mode: str) -> set:
        if mode == "DIARY":
            return {
                "diary",
                "summary_bullets",
                "key_conversations",
                "items",
                "clues",
                "troll_level_analysis",
                "consistency_check",
                "ending",
                "flags_for_next_day",
                "safety",
            }
        return {"title", "text", "ending_type", "reason"}

    def _candidate_score(self, mode: str, obj: Dict) -> int:
        """모드 스키마와의 적합도 점수(높을수록 우선)."""
        required = self._required_keys_for_mode(mode)
        return sum(1 for key in required if key in obj)

    def _extract_json_objects(self, text: str) -> List[Dict]:
        """
        모델 출력에서 JSON 객체 후보들을 최대한 복구하여 추출한다.
        - 코드블록/설명문이 섞여 있어도 중괄호 균형 기반으로 후보를 추출
        """
        if not text:
            raise ValueError("empty response")

        raw = text.strip()

        candidates = []

        # 1) 코드블록 우선 시도
        if "```json" in raw:
            try:
                block = raw.split("```json", 1)[1].split("```", 1)[0].strip()
                if block:
                    candidates.append(block)
            except Exception:
                pass
        if "```" in raw:
            try:
                block = raw.split("```", 1)[1].split("```", 1)[0].strip()
                if block:
                    candidates.append(block)
            except Exception:
                pass

        # 2) 전체 본문 후보
        candidates.append(raw)

        # 3) 첫 { ~ 마지막 } 범위 후보
        first = raw.find("{")
        last = raw.rfind("}")
        if first != -1 and last != -1 and first < last:
            candidates.append(raw[first:last + 1])

        # 4) 중괄호 균형으로 객체 후보 추출
        start = None
        depth = 0
        in_string = False
        escaped = False
        for idx, ch in enumerate(raw):
            if escaped:
                escaped = False
                continue
            if ch == "\\" and in_string:
                escaped = True
                continue
            if ch == "\"":
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                if depth == 0:
                    start = idx
                depth += 1
            elif ch == "}":
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start is not None:
                        candidates.append(raw[start:idx + 1])
                        start = None

        parsed_objects: List[Dict] = []
        seen = set()
        for candidate in candidates:
            cleaned = candidate.strip()
            if not cleaned:
                continue
            if cleaned in seen:
                continue
            seen.add(cleaned)
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict):
                    parsed_objects.append(parsed)
            except Exception:
                continue

        if not parsed_objects:
            raise ValueError("no valid json object found")
        return parsed_objects

    def _parse_json_from_text(self, text: str, mode: str) -> Dict:
        """
        JSON 객체 후보 중 모드 스키마에 가장 잘 맞는 객체를 선택한다.
        - {"mode":"DIARY","data":{...}} 형태면 data 내부를 우선 해석
        """
        objects = self._extract_json_objects(text)
        normalized: List[Dict] = []

        for obj in objects:
            normalized.append(obj)
            inner = obj.get("data")
            if isinstance(inner, dict):
                normalized.append(inner)

        best = max(normalized, key=lambda item: self._candidate_score(mode, item))
        if self._candidate_score(mode, best) == 0:
            raise ValueError("json parsed but no schema-matching fields found")
        return best

    def _fallback_story_payload(self, mode: str) -> Dict:
        """실모델 출력 파싱 실패 시 서비스 중단 방지용 안전 기본값."""
        now = datetime.now().isoformat()
        if mode == "DIARY":
            return {
                "day_index": 0,
                "diary": {
                    "title": "기록 정리",
                    "text": "오늘 수집한 대화 기록을 정리했지만, 일부 내용은 불명확하여 핵심만 보존했습니다.",
                    "tone": "neutral",
                },
                "summary_bullets": ["주요 대화가 기록되었으나 일부 응답 형식이 불안정했습니다."],
                "key_conversations": [],
                "items": [],
                "clues": [{"info": "응답 형식 불안정으로 단서 해석을 보수적으로 유지", "importance": "low"}],
                "troll_level_analysis": {"delta_total": 0, "top_causes": []},
                "consistency_check": {"contradictions_found": [], "missing_info": ["일부 원문 응답 파싱 실패"]},
                "ending": {"status": "continue", "ending_type": "null", "reason": "", "required_next_step": ""},
                "flags_for_next_day": [],
                "safety": {"hallucination_risk": "low", "spoiler_blocked": True},
                "time": now,
            }
        return {
            "title": "미완의 기록",
            "text": "최종 정리 과정에서 출력 형식 오류가 발생해 보수적 결론으로 마무리했습니다.",
            "ending_type": "failure",
            "reason": "모델 출력 JSON 파싱 실패",
            "time": now,
        }

    async def generate_story_content(self, mode: str, data: Any) -> Dict:
        """
        새로운 요구사항에 맞춘 통합 생성 메서드.
        mode: "DIARY" | "EPILOGUE"
        data: DIARY인 경우 메시지 텍스트, EPILOGUE인 경우 지난 일기들의 목록
        """
        # 1. 시스템 프롬프트 가져오기
        from app.core.database import db
        doc = await db["agent_prompts"].find_one({"_id": "story_agent"})
        base_system = (
            "You are the Story Agent for the infiltration investigation game \"Project: UMI\".\n"
            "Your role is record keeping and story synthesis.\n"
            "Summarize events into a SINGLE JSON object. No explanations or markdown."
        )
        if doc and "system" in doc:
            base_system = doc["system"]
        
        # 2. 모드별 스키마 강조
        schema_hint = ""
        if mode == "DIARY":
            schema_hint = "\n[REQUIRED SCHEMA - DIARY]\n{\n  \"diary\": { \"title\": \"...\", \"text\": \"...\", \"tone\": \"...\" },\n  \"summary_bullets\": [\"...\"],\n  \"key_conversations\": [{ \"with\": \"...\", \"what_changed\": \"...\", \"quote\": \"...\" }],\n  \"items\": [{ \"name\": \"...\", \"how_used_or_implication\": \"...\" }],\n  \"clues\": [{ \"info\": \"...\", \"importance\": \"low|mid|high\" }],\n  \"troll_level_analysis\": { \"delta_total\": 0, \"top_causes\": [] },\n  \"consistency_check\": { \"contradictions_found\": [], \"missing_info\": [] },\n  \"ending\": { \"status\": \"continue\", \"ending_type\": \"null\", \"reason\": \"\", \"required_next_step\": \"\" },\n  \"flags_for_next_day\": [],\n  \"safety\": { \"hallucination_risk\": \"low\", \"spoiler_blocked\": true }\n}"
        else:
            schema_hint = "\n[REQUIRED SCHEMA - EPILOGUE]\n{\n  \"title\": \"...\",\n  \"text\": \"...\",\n  \"ending_type\": \"escape|assimilation|exposed|sacrifice|failure|twist\",\n  \"reason\": \"...\"\n}"

        full_system = f"{base_system}\n{schema_hint}\n\nStrictly output ONLY the JSON object starting with {{ and ending with }}."

        # 3. Input Format 구성
        input_data = {
            "mode": mode,
            "data": data
        }
        user_prompt = json.dumps(input_data, ensure_ascii=False, indent=2)
        
        chat = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": user_prompt}
        ]
        
        full_system = f"{base_system}\n{schema_hint}\n\nStrictly output ONLY the JSON object. Do not include any text before or after the JSON."

        # 3. Input Format 구성
        input_data = {
            "mode": mode,
            "data": data
        }
        user_prompt = json.dumps(input_data, ensure_ascii=False, indent=2)
        
        chat = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": user_prompt}
        ]
        
        # [FIX] GPU 프록시의 첫 몇 글자 잘림 현상을 방지하기 위해 아주 긴 더미 헤더 추가 (sacrificial padding)
        padding = "PADDING_REPAIR_BUG_IGNORE_THIS_TEXT_AS_IT_IS_SACRIFICIAL_HEADER_FOR_TRUNCATION_FIX_"
        
        if self.tokenizer:
            try:
                full_prompt = f"<|im_start|>system\n{full_system}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n{padding}{{"
            except Exception:
                full_prompt = f"<|im_start|>system\n{full_system}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n{padding}{{"
        else:
            full_prompt = f"<|im_start|>system\n{full_system}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n{padding}{{"

        # JSON 생성을 위해 온도를 낮춤 (0.1)
        response_text = await self.generate(full_prompt, max_new_tokens=2048, temperature=0.1, top_p=0.95)
        
        # JSON 파싱
        try:
            return self._parse_json_from_text(response_text, mode)
        except Exception as e:
            print(f"[StoryAgent] JSON Parsing Failed(1st): {e}\nRaw: {response_text}")

        # 2차 시도: 출력 복구 전용 프롬프트로 재호출
        try:
            repair_prompt = (
                "You must output ONE valid JSON object only.\n"
                "No markdown, no comments, no explanation.\n"
                f"Mode: {mode}\n"
                "If any field is unknown, fill with safe defaults.\n"
                f"Original input data:\n{user_prompt}\n"
            )
            repaired_text = await self.generate(
                repair_prompt,
                max_new_tokens=1200,
                temperature=0.0,
                top_p=1.0
            )
            return self._parse_json_from_text(repaired_text, mode)
        except Exception as e:
            print(f"[StoryAgent] JSON Parsing Failed(2nd): {e}")
            return self._fallback_story_payload(mode)


    async def generate_diary_summary(self, messages: str, day_index: int, fish_level: int = None) -> dict:
        """
        기존 메서드 호환성 유지용 래퍼. 내부적으로 generate_story_content를 호출합니다.
        """
        result = await self.generate_story_content(mode="DIARY", data=messages)
        
        # 레거시 코드 호환성을 위해 day_index 보정
        if isinstance(result, dict) and "error" not in result:
            result["day_index"] = day_index
        return result

    def summarize_event(self, event_log: str) -> str:
        """
        특정 사건(NPC 대화 등)을 요약합니다. 장기 기억(Vector DB) 저장용.
        """
        system_prompt = (
            "당신은 미스터리 게임의 객관적인 관찰자입니다. "
            "주어지는 대화나 사건 로그를 2~3문장으로 요약해 주세요. "
            "누가, 어디서 만났고 어떤 핵심 정보가 오갔는지에 집중하세요. "
            "문체는 건조하고 사실적이어야 합니다."
        )
        
        user_prompt = f"Event Log:\n{event_log}"
        
        full_prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n"
        
        try:
            summary = self.generate(full_prompt, max_new_tokens=200)
            return summary.strip()
        except Exception as e:
            print(f"⚠️ [StoryAgent] Summary Failed: {e}")
            return "사건 요약 생성 실패."

# 싱글톤 인스턴스 생성
story_agent = StoryAgent()
