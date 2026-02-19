"""
GPU Inference Server (AWS EC2용)
- GA1 안전성 검사, NPC 대화 생성, Story 요약 추론을 GPU에서 수행
- 로컬 Mac에서 HTTP 요청으로 호출하여 사용
- 실행: uvicorn gpu_server:app --host 0.0.0.0 --port 8001
"""

import os
import torch
from typing import Optional, List, Dict
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.core.config import settings

app = FastAPI(title="UMI GPU Inference Server")

# ============================================================
# Request / Response 스키마
# ============================================================

class GA1Request(BaseModel):
    message: str

class GA1Response(BaseModel):
    is_safe: bool
    reason: Optional[str] = None

class NPCRequest(BaseModel):
    npc_id: str
    message: str
    history: Optional[List[Dict]] = None
    memory_context: Optional[str] = None  # 로컬에서 검색한 장기 기억 컨텍스트

class NPCResponse(BaseModel):
    response: str
    state: Optional[Dict] = None
    analysis: Optional[Dict] = None

class StoryRequest(BaseModel):
    prompt: str
    max_new_tokens: int = 256

class StoryDiaryRequest(BaseModel):
    messages: str
    fish_level: int = 3
    max_new_tokens: int = 400

class StoryResponse(BaseModel):
    text: str






# ============================================================
# 모델 로더 (서버 시작 시 GPU에 로드)
# ============================================================

class ModelManager:
    """서버 시작 시 모든 모델을 GPU 메모리에 로드합니다."""

    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[ModelManager] Device: {self.device}")

        self.ga1_model = None
        self.ga1_tokenizer = None
        self.npc_analyzer = None
        self.npc_prompt_loader = None
        self.npc_llm = None
        self.npc_pipelines: Dict = {}
        self.story_model = None
        self.story_tokenizer = None

    def load_ga1(self):
        """GA1 안전성 모델 로드"""
        from transformers import BertTokenizer, BertForSequenceClassification

        base_dir = os.path.dirname(os.path.abspath(__file__))
        local_model_path = os.path.join(base_dir, "app", "agents", "ga1_model")

        model_path = local_model_path if os.path.exists(local_model_path) else "beomi/kcbert-base"

        print(f"🔄 [GA1] Loading from {model_path}...")
        self.ga1_tokenizer = BertTokenizer.from_pretrained(model_path)
        self.ga1_model = BertForSequenceClassification.from_pretrained(model_path)
        self.ga1_model.to(self.device)
        self.ga1_model.eval()
        print(f"✅ [GA1] Loaded on {self.device}")

    def load_npc(self):
        """NPC 의도 분석기 + 프롬프트 로더 초기화 (v2)"""
        try:
            from app.agents.npc_dialogue_engine import IntentAnalyzer, NPCState
            from app.agents.npc_pipeline import NPCPromptLoader

            base_dir = os.path.dirname(os.path.abspath(__file__))
            checkpoint_path = os.path.join(base_dir, "app", "agents", "NPC_model_v2", "best_model.pt")
            threshold_json_path = os.path.join(base_dir, "app", "agents", "NPC_model_v2", "thresholds_standard.json")
            prompt_json_path = os.path.join(base_dir, "app", "data", "NPC_prompt.json")
            char_json_path = os.path.join(base_dir, "app", "data", "characters.json")

            if not os.path.exists(checkpoint_path):
                print(f"⚠️ [NPC] Checkpoint not found: {checkpoint_path}")
                checkpoint_path = None

            print("🔄 [NPC] Loading IntentAnalyzer (v2)...")
            self.npc_analyzer = IntentAnalyzer(
                encoder_model="monologg/koelectra-base-v3-discriminator",
                checkpoint_path=checkpoint_path,
                threshold_json_path=threshold_json_path,
                tag_k=3,
                tag_min_p=0.15
            )

            print("🔄 [NPC] Loading NPCPromptLoader...")
            # characters.json 경로 추가
            self.npc_prompt_loader = NPCPromptLoader(prompt_json_path, char_json_path)

            print("ℹ️ [NPC] IntentAnalyzer v2 + PromptLoader loaded. LLM will be shared with Story model.")
            print("✅ [NPC] Ready")
        except Exception as e:
            print(f"⚠️ [NPC] Loading failed: {e}")

    def load_story(self):
        """Story Agent 모델 로드 (GPU_SIZE 환경변수에 따라 3B/7B 선택)"""
        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
            from peft import PeftModel
            from dotenv import load_dotenv
            
            load_dotenv()
            
            # GPU_SIZE 설정 (기본값: SMALL - T4용)
            gpu_size = os.getenv("GPU_SIZE", "SMALL").upper()
            
            if gpu_size == "LARGE":
                # A10G 이상 (24GB+ VRAM): Qwen 2.5 7B
                base_model_id = "Qwen/Qwen2.5-7B-Instruct"
                use_adapter = False 
                use_4bit = True # 7B는 4bit 없이도 T4 2개나 A10G에 올라가지만 Safe하게 유지
                print(f"🚀 [Story] GPU_SIZE=LARGE detected. Using {base_model_id}.")
            else:
                # T4 (16GB VRAM): Gemma 2 2B (float16) - 빠르고 가벼움
                base_model_id = "google/gemma-2-2b-it"
                use_adapter = False
                use_4bit = False
                print(f"🚜 [Story] GPU_SIZE=SMALL detected. Using Gemma 2 2B (float16).")

            base_dir = os.path.dirname(os.path.abspath(__file__))
            model_dir = os.path.join(base_dir, "app", "agents", "story_agent_model")

            # LoRA adapter 탐색 (LARGE 모드일 때만 사용)
            adapter_path = None
            if use_adapter:
                if os.path.exists(model_dir):
                    if os.path.exists(os.path.join(model_dir, "adapter_config.json")):
                        adapter_path = model_dir
                    elif os.path.exists(os.path.join(model_dir, "final", "adapter_config.json")):
                        adapter_path = os.path.join(model_dir, "final")
                    else:
                        for d in sorted(os.listdir(model_dir), reverse=True):
                            sub = os.path.join(model_dir, d)
                            if os.path.isdir(sub) and os.path.exists(os.path.join(sub, "adapter_config.json")):
                                adapter_path = sub
                                break
            
            if adapter_path:
                print(f"📂 [Story] Adapter found: {adapter_path}")
            elif use_adapter:
                print(f"ℹ️ [Story] Adapter requested but not found. Using base model only.")

            # 토크나이저
            print(f"🔄 [Story] Loading tokenizer from {base_model_id}...")
            # 3B/7B 토크나이저는 호환되지만 안전하게 base_model에서 로드
            self.story_tokenizer = AutoTokenizer.from_pretrained(
                base_model_id, use_fast=True, trust_remote_code=True
            )
            if self.story_tokenizer.pad_token_id is None:
                self.story_tokenizer.pad_token = self.story_tokenizer.eos_token

            # 모델 로드
            print(f"🔄 [Story] Loading model: {base_model_id}...")
            
            # 4-bit 설정 (LARGE 모드일 때만)
            bnb_config = None
            if use_4bit and torch.cuda.is_available():
                bnb_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.bfloat16
                )

            model_kwargs = {
                "device_map": "auto",
                "trust_remote_code": True,
            }
            if bnb_config:
                model_kwargs["quantization_config"] = bnb_config
            else:
                model_kwargs["torch_dtype"] = torch.float16

            base_model = AutoModelForCausalLM.from_pretrained(
                base_model_id,
                **model_kwargs
            )

            if use_adapter and adapter_path:
                print(f"🔄 [Story] Loading LoRA adapter...")
                self.story_model = PeftModel.from_pretrained(base_model, adapter_path)
            else:
                self.story_model = base_model

            self.story_model.eval()

            if torch.cuda.is_available():
                used = torch.cuda.memory_allocated(0) / 1024**3
                total = torch.cuda.get_device_properties(0).total_memory / 1024**3
                print(f"✅ [Story] Loaded on {self.device} (VRAM: {used:.1f}/{total:.1f} GB)")
            else:
                print(f"✅ [Story] Loaded on {self.device}")
        except Exception as e:
            print(f"⚠️ [Story] Loading failed: {e}")

    def setup_npc_llm(self):
        """Story 모델을 NPC 대화 생성용 LangChain LLM으로 래핑"""
        if not self.story_model or not self.story_tokenizer:
            print("⚠️ [NPC-LLM] Story model not available. NPC LLM skipped.")
            return
        if not self.npc_analyzer:
            print("⚠️ [NPC-LLM] IntentAnalyzer not available. NPC LLM skipped.")
            return

        try:
            from transformers import pipeline as hf_pipeline, StoppingCriteria, StoppingCriteriaList
            from langchain_huggingface import HuggingFacePipeline

            # Stop Criteria 정의 (Gemma <end_of_turn> 토큰 ID 감지)
            # tokenizer.convert_tokens_to_ids("<end_of_turn>") usually returns 107
            stop_token_id = self.story_tokenizer.convert_tokens_to_ids("<end_of_turn>")
            
            class StopOnTokens(StoppingCriteria):
                def __init__(self, stop_ids):
                    self.stop_ids = stop_ids
                def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor, **kwargs) -> bool:
                    # 마지막 생성 토큰이 stop_id와 일치하면 중단
                    return input_ids[0, -1] == self.stop_ids

            stopping_criteria = StoppingCriteriaList([StopOnTokens(stop_token_id)])

            print(f"🔄 [NPC-LLM] Wrapping Story model with strict stopping on token ID {stop_token_id}...")
            
            pipe = hf_pipeline(
                "text-generation",
                model=self.story_model,
                tokenizer=self.story_tokenizer,
                max_new_tokens=160,
                temperature=0.7,
                top_p=0.9,
                repetition_penalty=1.1,
                return_full_text=False,
                stopping_criteria=stopping_criteria,  # [중요] 강제 중단 기준 적용
                pad_token_id=self.story_tokenizer.eos_token_id # pad_token 설정
            )
            
            # LangChain Wrapper
            self.npc_llm = HuggingFacePipeline(pipeline=pipe)
            
            print("✅ [NPC-LLM] NPC dialogue LLM ready (with StoppingCriteria)")
        except Exception as e:
            print(f"⚠️ [NPC-LLM] Setup failed: {e}")


# 전역 모델 매니저
model_mgr = ModelManager()


# ============================================================
# 서버 시작/종료 이벤트
# ============================================================

@app.on_event("startup")
async def startup():
    """서버 시작 시 모든 모델을 GPU에 로드"""
    print("=" * 60)
    print("🚀 GPU Inference Server Starting...")
    print(f"   Device: {model_mgr.device}")

    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        gpu_vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
        print(f"   ✅ GPU: {gpu_name}")
        print(f"   ✅ VRAM: {gpu_vram:.1f} GB")
    else:
        print("   ⚠️ CUDA GPU not detected! This server should run on AWS EC2 with GPU.")

    print("=" * 60)

    model_mgr.load_ga1()
    model_mgr.load_npc()
    model_mgr.load_story()
    model_mgr.setup_npc_llm()

    print("\n✅ All models loaded. Server ready.")


# ============================================================
# API 엔드포인트
# ============================================================

@app.get("/health")
async def health_check():
    """서버 상태 및 GPU 정보"""
    gpu_info = {}
    if torch.cuda.is_available():
        gpu_info = {
            "name": torch.cuda.get_device_name(0),
            "total_vram_gb": round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2),
            "used_vram_gb": round(torch.cuda.memory_allocated(0) / 1024**3, 2),
        }

    return {
        "status": "ok",
        "device": model_mgr.device,
        "gpu": gpu_info,
        "models": {
            "ga1": model_mgr.ga1_model is not None,
            "npc_analyzer": model_mgr.npc_analyzer is not None,
            "npc_llm": model_mgr.npc_llm is not None,
            "story": model_mgr.story_model is not None,
        }
    }


@app.post("/infer/ga1", response_model=GA1Response)
async def infer_ga1(req: GA1Request):
    """GA1: 유저 입력 안전성 검사"""
    if not model_mgr.ga1_model or not model_mgr.ga1_tokenizer:
        raise HTTPException(status_code=503, detail="GA1 model not loaded")

    try:
        inputs = model_mgr.ga1_tokenizer(
            req.message,
            return_tensors="pt",
            truncation=True,
            padding=True,
            max_length=128
        ).to(model_mgr.device)

        with torch.no_grad():
            logits = model_mgr.ga1_model(**inputs).logits
            prediction = torch.argmax(logits, dim=-1).item()

        if prediction == 1:
            return GA1Response(is_safe=False, reason="욕설이나 비속어가 포함되어 있습니다.")
        elif prediction == 2:
            return GA1Response(is_safe=False, reason="세계관에 어긋나거나 부적절한 표현이 감지되었습니다.")

        return GA1Response(is_safe=True)
    except Exception as e:
        print(f"[ERROR] GA1 inference: {e}")
        return GA1Response(is_safe=True)


@app.post("/infer/npc", response_model=NPCResponse)
async def infer_npc(req: NPCRequest):
    """NPC 대화 생성 (의도 분석 + LLM)"""
    if not model_mgr.npc_analyzer or not model_mgr.npc_llm:
        raise HTTPException(status_code=503, detail="NPC model not loaded")

    try:
        import asyncio
        from app.agents.npc_dialogue_engine import NPCState
        from app.agents.npc_pipeline import NPCDialoguePipeline
        from app.core.memory import memory_manager

        if req.npc_id not in model_mgr.npc_pipelines:
            model_mgr.npc_pipelines[req.npc_id] = NPCDialoguePipeline(
                analyzer=model_mgr.npc_analyzer,
                llm=model_mgr.npc_llm,
                prompt_loader=model_mgr.npc_prompt_loader,
                npc_id=req.npc_id,
                initial_state=NPCState(friendly=50, faith=50)
            )

        pipeline = model_mgr.npc_pipelines[req.npc_id]

        result = await asyncio.to_thread(
            pipeline.chat,
            req.message,
            history=req.history,
            memory_context=req.memory_context,
            max_new_tokens=160,
            do_sample=False
        )

        return NPCResponse(
            response=result["npc_response"],
            state=result.get("state"),
            analysis=result.get("analysis")
        )
    except Exception as e:
        print(f"[ERROR] NPC inference: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/infer/story", response_model=StoryResponse)
async def infer_story(req: StoryRequest):
    """스토리 텍스트 생성"""
    if not model_mgr.story_model or not model_mgr.story_tokenizer:
        raise HTTPException(status_code=503, detail="Story model not loaded")

    try:
        inputs = model_mgr.story_tokenizer(req.prompt, return_tensors="pt").to(model_mgr.story_model.device)

        with torch.no_grad():
            outputs = model_mgr.story_model.generate(
                **inputs,
                max_new_tokens=req.max_new_tokens,
                temperature=0.7,
                top_p=0.9,
                do_sample=True,
                repetition_penalty=1.05,
                eos_token_id=model_mgr.story_tokenizer.eos_token_id,
                pad_token_id=model_mgr.story_tokenizer.eos_token_id
            )

        generated_text = model_mgr.story_tokenizer.decode(outputs[0], skip_special_tokens=True)
        response_text = generated_text[len(req.prompt):].strip()

        return StoryResponse(text=response_text)
    except Exception as e:
        print(f"[ERROR] Story inference: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/infer/story/diary", response_model=StoryResponse)
async def infer_story_diary(req: StoryDiaryRequest):
    """스토리 일기 생성"""
    if not model_mgr.story_model or not model_mgr.story_tokenizer:
        raise HTTPException(status_code=503, detail="Story model not loaded")

    try:
        system_prompt = (
            "너는 텍스트 기반 잠입수사 게임 Project: UMI_PROTOCOL의 스토리 에이전트다. "
            "입력은 하루의 대화 로그(messages)이며, 이를 바탕으로 '일기'만 작성한다. "
            "톤은 어둡고 불안하며 잠입수사 기록처럼 건조해야 한다. "
            "밝은/훈훈/희망적 표현 금지. "
            "fish_level이 높을수록 감각 왜곡(어안렌즈, 비린내, 청각 왜곡 등)을 더 반영한다. "
            "출력은 JSON이 아니라 '일기 본문 텍스트만' 출력한다."
        )
        user_prompt = (
            f"[fish_level={req.fish_level}]\n"
            "아래 messages 로그만 근거로 일기를 작성해. 새 사실 창작 금지.\n"
            "조건: 7~10문장, 줄바꿈 없이 한 덩어리로.\n\n"
            f"{req.messages}"
        )

        chat = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        prompt = model_mgr.story_tokenizer.apply_chat_template(
            chat, tokenize=False, add_generation_prompt=True
        )

        inputs = model_mgr.story_tokenizer(prompt, return_tensors="pt").to(model_mgr.story_model.device)

        with torch.no_grad():
            outputs = model_mgr.story_model.generate(
                **inputs,
                max_new_tokens=req.max_new_tokens,
                temperature=0.7,
                top_p=0.9,
                do_sample=True,
                repetition_penalty=1.05,
                eos_token_id=model_mgr.story_tokenizer.eos_token_id,
                pad_token_id=model_mgr.story_tokenizer.eos_token_id
            )

        generated_text = model_mgr.story_tokenizer.decode(outputs[0], skip_special_tokens=True)
        response_text = generated_text[len(prompt):].strip()

        return StoryResponse(text=response_text)
    except Exception as e:
        print(f"[ERROR] Story diary inference: {e}")
        raise HTTPException(status_code=500, detail=str(e))





# ============================================================
# NPC Conversation: 다중 NPC 대화 생성
# ============================================================

class NPCConversationRequest(BaseModel):
    topic: str
    npc_ids: List[str]
    include_user: bool = False
    user_message: Optional[str] = None
    num_turns: int = 5
    history: Optional[List[Dict]] = None


class NPCConversationTurn(BaseModel):
    speaker: str
    speaker_id: str
    content: str
    analysis: Optional[Dict] = None


class NPCConversationResponse(BaseModel):
    topic: str
    turns: List[NPCConversationTurn]
    npc_states: Dict[str, Dict] = {}


# NPC ID → 한국어 이름 매핑
NPC_NAME_MAP = {
    "NPC_KWAK_01": "곽빙어",
    "NPC_CHEONG_02": "청갈치",
    "NPC_PARK_03": "박복어",
    "NPC_JEON_04": "전광어",
}


def _get_npc_korean_name(npc_id: str) -> str:
    """NPC ID에서 한국어 이름 조회"""
    if model_mgr.npc_prompt_loader:
        name = model_mgr.npc_prompt_loader.get_korean_name(npc_id)
        if name != npc_id:
            return name
    return NPC_NAME_MAP.get(npc_id, npc_id)


@app.post("/infer/npc/conversation", response_model=NPCConversationResponse)
async def infer_npc_conversation(req: NPCConversationRequest):
    """NPC 다중 대화 생성 (NPC-only 또는 User+NPC)"""
    if not model_mgr.npc_analyzer or not model_mgr.npc_llm:
        raise HTTPException(status_code=503, detail="NPC model not loaded")

    try:
        import asyncio
        from app.agents.npc_dialogue_engine import NPCState
        from app.agents.npc_pipeline import NPCDialoguePipeline
        from app.core.memory import memory_manager

        # NPC 파이프라인 준비
        for npc_id in req.npc_ids:
            if npc_id not in model_mgr.npc_pipelines:
                # 초기 상태 로드
                initial_state = model_mgr.npc_prompt_loader.get_initial_state(npc_id)
                
                model_mgr.npc_pipelines[npc_id] = NPCDialoguePipeline(
                    analyzer=model_mgr.npc_analyzer,
                    llm=model_mgr.npc_llm,
                    prompt_loader=model_mgr.npc_prompt_loader,
                    # retriever=None,  # Pipeline auto-loads world_lore.json
                    npc_id=npc_id,
                    initial_state=initial_state
                )

        turns: List[NPCConversationTurn] = []
        conversation_history: List[Dict[str, str]] = [
            {"speaker": "system", "content": f"[대화 주제] {req.topic}"}
        ]

        # 이전 히스토리 추가
        if req.history:
            for h in req.history:
                conversation_history.append({
                    "speaker": h.get("speaker_id", h.get("speaker", "unknown")),
                    "content": h.get("content", "")
                })

        if req.include_user and req.user_message:
            # ── User+NPC 모드 ──
            conversation_history.append({
                "speaker": "user",
                "content": req.user_message
            })
            turns.append(NPCConversationTurn(
                speaker="user",
                speaker_id="user",
                content=req.user_message,
                analysis=None
            ))

            for npc_id in req.npc_ids:
                pipeline = model_mgr.npc_pipelines[npc_id]
                result = await asyncio.to_thread(
                    pipeline.chat,
                    req.user_message,
                    history=conversation_history,
                    max_new_tokens=160,
                    do_sample=False
                )

                korean_name = _get_npc_korean_name(npc_id)
                turns.append(NPCConversationTurn(
                    speaker=korean_name,
                    speaker_id=npc_id,
                    content=result["npc_response"],
                    analysis=result.get("analysis")
                ))
                conversation_history.append({
                    "speaker": npc_id,
                    "content": result["npc_response"]
                })
        else:
            # ── NPC-only 자동 대화 모드 ──
            for turn_idx in range(req.num_turns):
                current_npc_id = req.npc_ids[turn_idx % len(req.npc_ids)]
                pipeline = model_mgr.npc_pipelines[current_npc_id]

                if turn_idx == 0:
                    message = f"[대화 주제: {req.topic}] 이 주제에 대해 이야기해 봐."
                else:
                    message = turns[-1].content

                result = await asyncio.to_thread(
                    pipeline.chat,
                    message,
                    history=conversation_history,
                    max_new_tokens=160,
                    do_sample=False
                )

                korean_name = _get_npc_korean_name(current_npc_id)
                turns.append(NPCConversationTurn(
                    speaker=korean_name,
                    speaker_id=current_npc_id,
                    content=result["npc_response"],
                    analysis=result.get("analysis")
                ))
                conversation_history.append({
                    "speaker": current_npc_id,
                    "content": result["npc_response"]
                })

        # NPC 상태 수집
        npc_states = {}
        for npc_id in req.npc_ids:
            if npc_id in model_mgr.npc_pipelines:
                npc_states[npc_id] = model_mgr.npc_pipelines[npc_id].state.to_dict()

        return NPCConversationResponse(
            topic=req.topic,
            turns=turns,
            npc_states=npc_states
        )

    except Exception as e:
        print(f"[ERROR] NPC conversation inference: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
