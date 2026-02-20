"""
NPC 대화 통합 파이프라인 (v2 Enhanced + Dynamic Persona RAG)
- IntentAnalyzer (per-tag threshold + top-k) + LangChain LLM 결합
- NPC_prompt.json 기반 동적 페르소나 로딩
  - Core (정적): PERSONALITY, SPEECH_STYLE → 항상 포함
  - Dynamic (RAG): BEHAVIOR_RULES, INFO_POLICY → 메타데이터 필터 + 유사도 검색
- RAG (World Lore) 기반 세계관 지식 검색 (SentenceTransformer + Numpy)
"""

import os
import re
import json
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Type, List, Tuple, Callable
from app.agents.npc_dialogue_engine import (
    IntentAnalyzer, 
    NPCState,
    get_relationship_bucket,
    sanitize_npc_response,
    format_control_signal
)

# LangChain 관련 import
from langchain_core.runnables import Runnable
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.output_parsers import StrOutputParser

# RAG 관련
try:
    import numpy as np
    from sentence_transformers import SentenceTransformer
except ImportError:
    np = None
    SentenceTransformer = None
    print("⚠️ [RAG] numpy 또는 sentence_transformers 모듈이 없습니다. RAG 기능이 비활성화됩니다.")


# ============================================================
# 0. Document 데이터 구조
# ============================================================

@dataclass
class Document:
    """메타데이터가 포함된 문서 단위"""
    text: str
    metadata: Dict[str, str] = field(default_factory=dict)


# ============================================================
# 1. RAG Retriever (V3 Enhanced - Metadata Filtering)
# ============================================================

class RAGRetriever:
    """
    Sentence-BERT 기반 RAG 검색기 (Numpy 코사인 유사도)
    - List[str] 또는 List[Document]를 받아 인덱싱
    - retrieve() 시 filter_fn 콜백으로 메타데이터 필터링 가능
    """
    def __init__(
        self,
        docs,  # List[str] 또는 List[Document]
        embed_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        shared_model: Optional[Any] = None
    ):
        # docs 정규화: str -> Document 변환
        if docs and isinstance(docs[0], str):
            self._docs: List[Document] = [Document(text=d) for d in docs]
        else:
            self._docs: List[Document] = list(docs) if docs else []

        self.enabled = (SentenceTransformer is not None) and (len(self._docs) > 0)
        self.embed_model_name = embed_model_name
        self.normalize = True

        self.model = None
        self.emb: Optional["np.ndarray"] = None

        if not self.enabled:
            print("[INFO] RAG disabled (No docs or No module).")
            return

        # 공유 모델이 있으면 재사용 (메모리 절약)
        if shared_model is not None:
            self.model = shared_model
        else:
            print(f"[RAG] Loading Embedding Model: {embed_model_name}...")
            self.model = SentenceTransformer(embed_model_name)

        texts = [d.text for d in self._docs]
        print(f"[RAG] Encoding {len(texts)} chunks...")
        self.emb = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False).astype("float32")

        if self.normalize:
            norm = np.linalg.norm(self.emb, axis=1, keepdims=True) + 1e-12
            self.emb = self.emb / norm

        print(f"[RAG] Ready. {len(self._docs)} chunks indexed.")

    @property
    def chunks(self) -> List[str]:
        """하위 호환: 텍스트 리스트 반환"""
        return [d.text for d in self._docs]

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        filter_fn: Optional[Callable[[Dict[str, str]], bool]] = None
    ) -> List[Tuple[str, float]]:
        """
        유사도 기반 검색.
        filter_fn: metadata dict -> bool (True면 포함)
        """
        if not self.enabled or not query or not query.strip():
            return []

        q = self.model.encode([query], convert_to_numpy=True, show_progress_bar=False).astype("float32")
        if self.normalize:
            q = q / (np.linalg.norm(q, axis=1, keepdims=True) + 1e-12)

        # 필터링할 인덱스 결정
        if filter_fn:
            candidates = [i for i, d in enumerate(self._docs) if filter_fn(d.metadata)]
        else:
            candidates = list(range(len(self._docs)))

        if not candidates:
            return []

        # 후보만 점수 계산
        candidate_emb = self.emb[candidates]  # (C, D)
        scores = candidate_emb @ q[0]         # (C,)

        k = max(1, min(len(candidates), int(top_k)))
        top_idx = np.argsort(-scores)[:k]

        return [(self._docs[candidates[i]].text, float(scores[i])) for i in top_idx]


# ============================================================
# 2. NPC 프롬프트 로더 (Updated for V3 Format)
# ============================================================

class NPCPromptLoader:
    """
    V3 형식의 NPC_prompt.json 로더 (Dynamic Persona RAG 지원)
    
    구조: { "npc_id": { "bad": "...", "normal": "...", ... }, ... }
    
    프롬프트를 정적(Core)과 동적(Rules)으로 분리:
    - Core (항상 포함): [NPC_ID], [PERSONALITY], [SPEECH_STYLE]
    - Dynamic (RAG 검색): [BEHAVIOR_RULES], [INFO_POLICY] 내의 개별 규칙
    """
    
    # 프롬프트에서 분리할 섹션 헤더
    _SECTION_PATTERN = re.compile(
        r'\[(?:NPC_ID|PERSONALITY|BEHAVIOR_RULES|SPEECH_STYLE|INFO_POLICY)\]'
    )
    # Core (정적) 섹션 - 항상 시스템 프롬프트에 포함
    _CORE_SECTIONS = {"[NPC_ID]", "[PERSONALITY]", "[SPEECH_STYLE]"}
    # Dynamic (RAG 검색) 섹션 - Vector DB에 청킹하여 저장
    _DYNAMIC_SECTIONS = {"[BEHAVIOR_RULES]", "[INFO_POLICY]"}
    
    def __init__(self, json_path: str, characters_json_path: Optional[str] = None):
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"NPC 프롬프트 JSON 파일을 찾을 수 없습니다: {json_path}")
        
        with open(json_path, "r", encoding="utf-8") as f:
            self._prompts = json.load(f)
        
        # ID Normalization (lowercase keys)
        self._prompts_lower = {k.lower(): v for k, v in self._prompts.items()}
        
        # characters.json 로드 (ID -> 한국어 이름 매핑용)
        self._id_to_korean: Dict[str, str] = {}
        self._character_stats: Dict[str, NPCState] = {}
        
        if characters_json_path and os.path.exists(characters_json_path):
            try:
                with open(characters_json_path, "r", encoding="utf-8") as f:
                    char_data = json.load(f)
                
                for key, info in char_data.items():
                    name_kr = info.get("name_kr", key)
                    self._id_to_korean[key.lower()] = name_kr
                    self._id_to_korean[key.upper()] = name_kr
                    
                    stats = info.get("stats", {})
                    self._character_stats[key.lower()] = NPCState(
                        friendly=stats.get("friendly", 50),
                        faith=stats.get("faith", 50)
                    )
                    
                print(f"[NPCPromptLoader] Loaded metadata for {len(char_data)} characters.")
            except Exception as e:
                print(f"⚠️ [NPCPromptLoader] Failed to load characters.json: {e}")
        
        # ── 청킹: Core / Dynamic 분리 ──
        self._core_prompts: Dict[str, Dict[str, str]] = {}   # {npc_id: {bucket: core_text}}
        self._persona_docs: List[Document] = []               # Dynamic 규칙 청크
        self._chunk_all_prompts()
        
        # ── Persona RAG DB 초기화 ──
        self.persona_rag: Optional[RAGRetriever] = None
        if self._persona_docs:
            self.persona_rag = RAGRetriever(self._persona_docs)
            print(f"[NPCPromptLoader] PersonaRAG indexed {len(self._persona_docs)} rule chunks.")
        
        print(f"[NPCPromptLoader] Loaded prompts for {len(self._prompts)} NPCs.")

    # ──────────────────────────────────────────
    # 프롬프트 청킹 로직
    # ──────────────────────────────────────────
    def _parse_sections(self, prompt_text: str) -> Dict[str, str]:
        """
        하나의 프롬프트 텍스트를 섹션별로 분리.
        예: {"[NPC_ID]": "Name: 곽빙어", "[PERSONALITY]": "냉소적...", ...}
        """
        sections: Dict[str, str] = {}
        current_header = None
        current_lines: List[str] = []
        
        for line in prompt_text.split("\n"):
            stripped = line.strip()
            if self._SECTION_PATTERN.match(stripped):
                # 이전 섹션 저장
                if current_header:
                    sections[current_header] = "\n".join(current_lines).strip()
                current_header = stripped
                current_lines = []
            else:
                current_lines.append(line)
        
        # 마지막 섹션 저장
        if current_header:
            sections[current_header] = "\n".join(current_lines).strip()
        
        return sections
    
    def _chunk_all_prompts(self):
        """
        모든 NPC의 모든 버킷 프롬프트를 파싱하여
        Core(정적)와 Dynamic(RAG 청크)으로 분리.
        """
        for npc_id, buckets in self._prompts_lower.items():
            self._core_prompts[npc_id] = {}
            
            for bucket, full_text in buckets.items():
                sections = self._parse_sections(full_text)
                
                # --- Core 프롬프트 조합 (항상 포함) ---
                core_parts = []
                for header in ["[NPC_ID]", "[PERSONALITY]", "[SPEECH_STYLE]"]:
                    if header in sections:
                        core_parts.append(f"{header}\n{sections[header]}")
                self._core_prompts[npc_id][bucket] = "\n\n".join(core_parts)
                
                # --- Dynamic 규칙 청킹 (개별 룰 -> Document) ---
                for header in ["[BEHAVIOR_RULES]", "[INFO_POLICY]"]:
                    if header not in sections:
                        continue
                    section_text = sections[header]
                    # 줄 단위("- ...")로 분리
                    rules = [r.strip() for r in section_text.split("\n") if r.strip().startswith("- ") or r.strip().startswith("기본 구조")]
                    if not rules:
                        # 분리 불가 시 전체를 하나의 청크로
                        rules = [section_text]
                    
                    for rule in rules:
                        self._persona_docs.append(Document(
                            text=f"[{header}] {rule}",
                            metadata={
                                "npc_id": npc_id,
                                "bucket": bucket,
                                "section": header
                            }
                        ))

    # ──────────────────────────────────────────
    # 공개 API
    # ──────────────────────────────────────────
    def get_initial_state(self, npc_id: str) -> NPCState:
        """초기 상태 반환"""
        return self._character_stats.get(npc_id.lower(), NPCState(friendly=50, faith=50))

    def get_core_prompt(self, npc_id: str, friendly: int) -> str:
        """
        정적 Core 프롬프트 반환 (PERSONALITY + SPEECH_STYLE).
        항상 시스템 프롬프트에 포함됩니다.
        """
        npc_key = npc_id.lower()
        cores = self._core_prompts.get(npc_key)
        if not cores:
            return f"[NPC_ID]\nID: {npc_id}\n(프롬프트 데이터가 없습니다)\n[SPEECH_STYLE]\n- 한국어로 대화."
        
        bucket = get_relationship_bucket(friendly)
        if bucket in cores:
            return cores[bucket]
        return cores.get("normal", cores.get("bad", next(iter(cores.values()))))

    def retrieve_dynamic_rules(
        self,
        npc_id: str,
        friendly: int,
        user_message: str,
        top_k: int = 5
    ) -> str:
        """
        동적 행동 규칙 검색 (RAG).
        현재 NPC ID + 친밀도 버킷으로 필터링 후, 유사도 기반 검색.
        """
        if not self.persona_rag or not self.persona_rag.enabled:
            # RAG 비활성시 기존 방식으로 fallback
            return self.build_persona_prompt(npc_id, friendly)
        
        bucket = get_relationship_bucket(friendly)
        npc_key = npc_id.lower()
        
        def _filter(meta: Dict[str, str]) -> bool:
            return meta.get("npc_id") == npc_key and meta.get("bucket") == bucket
        
        results = self.persona_rag.retrieve(user_message, top_k=top_k, filter_fn=_filter)
        
        if not results:
            return ""  # No dynamic rules found
        
        rules_text = "\n".join([text for text, score in results])
        return f"[DYNAMIC_GUIDELINES (친밀도: {bucket})]\n{rules_text}"

    def build_persona_prompt(self, npc_id: str, friendly: int) -> str:
        """
        [하위 호환] friendly 점수에 따른 전체 페르소나 프롬프트 반환.
        Dynamic RAG를 사용하지 않는 경우의 fallback.
        """
        prompts = self._prompts_lower.get(npc_id.lower())
        if not prompts:
            return f"[NPC_ID]\nID: {npc_id}\n(프롬프트 데이터가 없습니다)\n[SPEECH_STYLE]\n- 한국어로 대화."
            
        bucket = get_relationship_bucket(friendly)
        
        if bucket in prompts:
            return prompts[bucket]
        if "normal" in prompts:
            return prompts["normal"]
        if "bad" in prompts:
            return prompts["bad"]
        
        return next(iter(prompts.values()))

    def get_korean_name(self, npc_id: str) -> str:
        """NPC ID → 한국어 이름 반환"""
        return self._id_to_korean.get(npc_id.lower(), npc_id)

    def get_all_npc_ids(self) -> List[str]:
        """모든 NPC ID 반환"""
        return list(self._prompts_lower.keys())


# ============================================================
# 3. 통합 파이프라인 (Updated)
# ============================================================

class NPCDialoguePipeline:
    """
    NPC 대화 생성 통합 파이프라인 (v2 Enhanced)
    - V3 Prompts + RAG + V2 Logic
    """
    
    def __init__(
        self,
        analyzer: IntentAnalyzer,
        llm: Runnable,
        prompt_loader: NPCPromptLoader,
        retriever: Optional[RAGRetriever] = None,
        npc_id: str = "CHEONGGALCHI",
        initial_state: NPCState = None
    ):
        self.analyzer = analyzer
        self.llm = llm
        self.prompt_loader = prompt_loader
        self.retriever = retriever
        self.npc_id = npc_id
        self.state = initial_state or NPCState()
        
        self.korean_name = self.prompt_loader.get_korean_name(npc_id)
        self.debug = False
        
        # RAG가 외부에서 주입되지 않았으면, 기본 Lore 파일 로드 시도
        if not self.retriever:
            try:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                # data_dir is usually ../../data from current file's location in app/agents
                lore_path = os.path.join(os.path.dirname(os.path.dirname(base_dir)), "data", "world_lore.json")
                
                # Check absolute path fallback
                if not os.path.exists(lore_path):
                     lore_path = os.path.join(base_dir, "../data/world_lore.json")

                if os.path.exists(lore_path):
                    with open(lore_path, "r", encoding="utf-8") as f:
                        docs = json.load(f)
                    self.retriever = RAGRetriever(docs)
                    print(f"[Pipeline] Auto-loaded RAG with {len(docs)} lore docs.")
                else:
                    print(f"[Pipeline] RAG disabled. world_lore.json not found at {lore_path}")
            except Exception as e:
                print(f"⚠️ [Pipeline] Failed to auto-load RAG: {e}")

    def _build_system_prompt(
        self,
        user_message: str,
        analysis: Dict[str, Any],
        context: str = "",
        friendly: int = None
    ) -> str:
        # Use provided friendly or default to current state
        target_friendly = friendly if friendly is not None else self.state.friendly

        # 1. Core 페르소나 (정적: PERSONALITY + SPEECH_STYLE)
        core = self.prompt_loader.get_core_prompt(self.npc_id, target_friendly)
        
        # 2. Dynamic 행동 규칙 (RAG 기반 검색)
        dynamic_rules = self.prompt_loader.retrieve_dynamic_rules(
            self.npc_id, target_friendly, user_message, top_k=5
        )
        
        # 3. 컨트롤 시그널
        control_signal = format_control_signal(
            analysis["reason_tags"],
            analysis["friendly_delta"],
            analysis["faith_delta"]
        )
        
        # 4. 조합
        system_prompt = core.strip()
        
        if dynamic_rules:
            system_prompt += "\n\n" + dynamic_rules.strip()
        
        if context:
            system_prompt += "\n\n[WORLD_CONTEXT(RAG)]\n" + context.strip()
            
        system_prompt += "\n\n" + control_signal.strip()
        
        # Output Constraints (Korean Enforcement)
        system_prompt += "\n\n" + (
            "[최종 출력 규칙]\n"
            f"- {self.npc_id}의 대사는 오직 '한국어'로만 출력하십시오.\n"
            "- 절대로 영어나 중국어를 사용하지 마십시오.\n"
            "- 마크다운, 선택지, 설명, 지문 등을 포함하지 마십시오.\n"
        )
        
        return system_prompt.strip()
    
    def chat(
        self,
        user_message: str,
        history: Optional[List[Dict[str, str]]] = None,
        memory_context: Optional[str] = None,
        max_new_tokens: int = 200,
        do_sample: bool = True,
        update_state: bool = True,
        forced_state: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Conversation Main Loop"""
        
        # 1. Intent Analysis
        analysis = self.analyzer.analyze(user_message)
        
        # 2. State Update (Conditional)
        if update_state:
            self.state.apply_delta(
                analysis["friendly_delta"],
                analysis["faith_delta"]
            )
        else:
            if self.debug:
                print(f"[Pipeline] State update disabled. Delta: friendly={analysis['friendly_delta']}, faith={analysis['faith_delta']}")
        
        # Determine Current State for Prompt Generation
        current_friendly = self.state.friendly
        current_faith = self.state.faith
        
        if forced_state:
            current_friendly = forced_state.get("friendly", current_friendly)
            current_faith = forced_state.get("faith", current_faith)
            if self.debug:
                print(f"[Pipeline] Using Forced State: friendly={current_friendly}, faith={current_faith}")

        # 3. RAG Retrieval (V3 style)
        context_text = ""
        if self.retriever and self.retriever.enabled:
            # Query Expansion: Bilingual
            search_query = f"About {self.npc_id} {self.korean_name}. {user_message}"
            results = self.retriever.retrieve(search_query, top_k=3)
            # Result Formatting
            context_text = "\n".join([f"- {doc}" for doc, score in results])
            if self.debug and results:
                print(f"[RAG] Found {len(results)} docs (top score: {results[0][1]:.3f})")

        # 4. Long-term Memory Merge
        if memory_context:
            if context_text:
                context_text += "\n\n[USER_MEMORY]\n" + memory_context
            else:
                context_text = "[USER_MEMORY]\n" + memory_context

        # 5. System Prompt Construction
        system_prompt = self._build_system_prompt(
            user_message, 
            analysis, 
            context=context_text,
            friendly=current_friendly
        )
        
        # 6. LLM Prompt Construction (Gemma-style)
        full_prompt = f"<start_of_turn>user\n{system_prompt}<end_of_turn>\n"
        full_prompt += f"<start_of_turn>model\n알겠습니다. 이제부터 {self.npc_id}가 되어 한국어로만 대화하겠습니다.<end_of_turn>\n"
        
        if history:
            for msg in history[-10:]:
                role = "user" if msg.get("speaker") == "user" else "model"
                content = msg.get("content", "")
                full_prompt += f"<start_of_turn>{role}\n{content}<end_of_turn>\n"
        
        full_prompt += f"<start_of_turn>user\n{user_message}<end_of_turn>\n<start_of_turn>model\n"
        
        # 7. 생성
        prompt_template = PromptTemplate(input_variables=["user_input"], template=full_prompt)
        chain = prompt_template | self.llm | StrOutputParser()
        raw_response = chain.invoke({"user_input": user_message})
        
        # 8. 후처리
        npc_response = sanitize_npc_response(raw_response)
        
        if self.debug:
            print(f"[DEBUG] System Prompt:\n{system_prompt[:200]}...")
            print(f"[DEBUG] Raw Response:\n{raw_response}")

        # 9. 결과 반환
        result = {
            "npc_response": npc_response,
            "state": self.state.to_dict(),
            "analysis": {
                "reason_tags": analysis["reason_tags"],
                "friendly_delta": analysis["friendly_delta"],
                "faith_delta": analysis["faith_delta"],
                "relationship_bucket": get_relationship_bucket(self.state.friendly)
            }
        }
        
        if self.debug:
            result["debug"] = {
                "rag_context": context_text,
                "raw": raw_response
            }
            
        return result


if __name__ == "__main__":
    import sys
    # 간이 테스트용
    print("=== NPC Pipeline V2 Enhanced Test ===")
    
    # Mock LLM
    class MockLLM:
        def invoke(self, x):
            return "테스트 응답입니다."
    
    # Mock Analyzer
    class MockAnalyzer:
        def analyze(self, text):
            return {
                "reason_tags": ["TEST"],
                "friendly_delta": 0,
                "faith_delta": 0,
                "tag_probs": {}
            }

    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(os.path.dirname(os.path.dirname(base_dir)), "data")
    prompt_json = os.path.join(data_dir, "NPC_prompt.json")
    char_json = os.path.join(data_dir, "characters.json")
    
    if os.path.exists(prompt_json):
        loader = NPCPromptLoader(prompt_json, char_json)
        # Note: If extract_v3_data.py was run, lowercase keys are normalized
        print(f"Loader initialized. IDs: {list(loader._id_to_korean.keys())}")
        
        pipeline = NPCDialoguePipeline(
            analyzer=MockAnalyzer(),
            llm=MockLLM(),
            prompt_loader=loader,
            npc_id="CheongGalchi"
        )
        
        print(f"Pipeline ready for {pipeline.korean_name}")
        res = pipeline.chat("안녕?")
        print("Response:", res["npc_response"])
    else:
        print(f"NPC_prompt.json not found at {prompt_json}")
