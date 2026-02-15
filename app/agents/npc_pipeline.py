"""
NPC 대화 통합 파이프라인 (v2)
- IntentAnalyzer (per-tag threshold + top-k) + LangChain LLM 결합
- NPC_prompt.json 기반 동적 페르소나 로딩 (4단계: BAD/NORMAL/GOOD/PERFECT)
- RAG 기반 세계관 지식 검색
"""

import os
import json
from typing import Dict, Any, Optional, Type, List
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
from langchain_core.retrievers import BaseRetriever


# ============================================================
# NPC 프롬프트 로더 (NPC_prompt.json)
# ============================================================

class NPCPromptLoader:
    """
    NPC_prompt.json에서 NPC별 페르소나 프롬프트를 동적으로 로드한다.
    
    JSON 구조:
    {
        "npcs": {
            "청갈치": {
                "id": "CheongGalchi",
                "role": "...",
                "affinity_levels": {
                    "BAD":     { "range": "0-19",   "personality": "...", "behavior_rules": [...], ... },
                    "NORMAL":  { "range": "20-45",  ... },
                    "GOOD":    { "range": "46-75",  ... },
                    "PERFECT": { "range": "76-100", ... }
                }
            },
            ...
        }
    }
    """
    
    def __init__(self, json_path: str, characters_json_path: Optional[str] = None):
        """
        NPC_prompt.json 로드 및 ID→데이터 매핑 구축
        characters_json_path가 제공되면 초기 스탯 정보도 로드
        """
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"NPC 프롬프트 JSON 파일을 찾을 수 없습니다: {json_path}")
        
        with open(json_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        
        self._npcs_by_korean_name: Dict[str, Dict] = raw.get("npcs", {})
        
        # id → (korean_name, npc_data) 매핑 구축
        self._npcs_by_id: Dict[str, tuple] = {}
        for kr_name, npc_data in self._npcs_by_korean_name.items():
            npc_id = npc_data.get("id", "")
            self._npcs_by_id[npc_id] = (kr_name, npc_data)
            # 대문자 버전도 매핑 (CHEONGGALCHI → CheongGalchi)
            self._npcs_by_id[npc_id.upper()] = (kr_name, npc_data)
        
        # characters.json 로드 (초기 스탯용)
        self._character_stats: Dict[str, Dict] = {}
        if characters_json_path and os.path.exists(characters_json_path):
            try:
                with open(characters_json_path, "r", encoding="utf-8") as f:
                    char_data = json.load(f)
                
                # Korean Name -> Stats 매핑 생성
                # characters.json 구조: {"KEY": {"name_kr": "...", "stats": ...}}
                for key, info in char_data.items():
                    name_kr = info.get("name_kr")
                    stats = info.get("stats", {})
                    if name_kr:
                        self._character_stats[name_kr] = stats
                
                print(f"[NPCPromptLoader] Loaded stats for {len(self._character_stats)} characters from characters.json")
            except Exception as e:
                print(f"⚠️ [NPCPromptLoader] Failed to load characters.json: {e}")
        
        print(f"[NPCPromptLoader] Loaded {len(self._npcs_by_korean_name)} NPCs from {json_path}")
        for kr_name, npc_data in self._npcs_by_korean_name.items():
            print(f"  - {kr_name} (id={npc_data.get('id')})")
    
    def _friendly_to_level(self, friendly: int) -> str:
        """
        friendly 값을 affinity level로 변환.
        get_relationship_bucket과 동일한 경계값 사용.
        """
        bucket = get_relationship_bucket(friendly)
        # bucket (bad/normal/good/perfect) → JSON key (BAD/NORMAL/GOOD/PERFECT)
        return bucket.upper()
    
    def get_npc_data(self, npc_id: str) -> Optional[tuple]:
        """NPC ID로 (한국어 이름, NPC 데이터) 반환"""
        return self._npcs_by_id.get(npc_id) or self._npcs_by_id.get(npc_id.upper())
    
    def get_initial_state(self, npc_id: str) -> NPCState:
        """
        NPC ID에 해당하는 초기 상태(NPCState) 반환
        characters.json 데이터가 있으면 사용, 없으면 기본값(50/50)
        """
        kr_name = self.get_korean_name(npc_id)
        stats = self._character_stats.get(kr_name)
        
        if stats:
            return NPCState(
                friendly=stats.get("friendly", 50),
                faith=stats.get("faith", 50)
            )
        
        # Fallback
        return NPCState(friendly=50, faith=50)

    def build_persona_prompt(self, npc_id: str, friendly: int) -> str:
        """
        NPC ID와 friendly 점수에 따라 시스템 프롬프트를 생성한다.
        
        Returns:
            구조화된 페르소나 프롬프트 문자열
        """
        result = self.get_npc_data(npc_id)
        if not result:
            return f"[NPC_ID]\n이름: {npc_id}\n\n(프롬프트 데이터 없음 — 기본 모드로 대화합니다)"
        
        kr_name, npc_data = result
        role = npc_data.get("role", "")
        
        # affinity level 결정
        level_key = self._friendly_to_level(friendly)
        levels = npc_data.get("affinity_levels", {})
        level_data = levels.get(level_key)
        
        if not level_data:
            # fallback: NORMAL
            level_data = levels.get("NORMAL", {})
            level_key = "NORMAL"
        
        # 프롬프트 조합
        personality = level_data.get("personality", "")
        behavior_rules = level_data.get("behavior_rules", [])
        speech_style = level_data.get("speech_style", "")
        info_policy = level_data.get("info_policy", "")
        
        prompt_parts = []
        
        # [NPC_ID]
        prompt_parts.append(f"[NPC_ID]\n이름: {kr_name}\n정체: {role}")
        
        # [PERSONALITY]
        if personality:
            prompt_parts.append(f"[PERSONALITY]\n{personality}")
        
        # [BEHAVIOR_RULES]
        if behavior_rules:
            rules_str = "\n".join(f"- {r}" for r in behavior_rules)
            prompt_parts.append(f"[BEHAVIOR_RULES]\n{rules_str}")
        
        # [SPEECH_STYLE]
        if speech_style:
            prompt_parts.append(f"[SPEECH_STYLE]\n{speech_style}")
        
        # [INFO_POLICY]
        if info_policy:
            prompt_parts.append(f"[INFO_POLICY]\n{info_policy}")
        
        return "\n\n".join(prompt_parts)
    
    def get_korean_name(self, npc_id: str) -> str:
        """NPC ID → 한국어 이름 반환"""
        result = self.get_npc_data(npc_id)
        if result:
            return result[0]
        return npc_id
    
    def get_all_npc_ids(self) -> List[str]:
        """NPC_prompt.json에 정의된 모든 NPC ID 목록 반환"""
        ids = []
        for info in self._npcs_by_korean_name.values():
            if "id" in info:
                ids.append(info["id"])
        return ids


# ============================================================
# 통합 파이프라인 (v2)
# ============================================================

class NPCDialoguePipeline:
    """
    NPC 대화 생성 통합 파이프라인 (v2)
    
    워크플로우:
    1. 사용자 입력 → IntentAnalyzer → 의도/감정 분석 (per-tag threshold)
    2. 분석 결과 + 현재 상태 → 컨트롤 시그널 생성
    3. RAG 검색 (세계관 지식)
    4. NPC_prompt.json에서 페르소나 동적 선택 (friendly → affinity level)
    5. LLM → 대화 생성
    6. 후처리 (불필요한 텍스트 제거)
    7. 상태 업데이트
    """
    
    def __init__(
        self,
        analyzer: IntentAnalyzer,
        llm: Runnable,
        prompt_loader: NPCPromptLoader,
        retriever: Optional[BaseRetriever] = None,
        npc_id: str = "CHEONGGALCHI",
        initial_state: NPCState = None
    ):
        self.analyzer = analyzer
        self.llm = llm
        self.prompt_loader = prompt_loader
        self.retriever = retriever
        self.npc_id = npc_id
        self.state = initial_state or NPCState()
        
        # 한국어 이름 캐시
        self.korean_name = self.prompt_loader.get_korean_name(npc_id)
        
        # 디버그 모드
        self.debug = False
    
    def _build_system_prompt(
        self,
        user_message: str,
        analysis: Dict[str, Any],
        context: str = ""
    ) -> str:
        """
        시스템 프롬프트 구성 (동적 JSON 기반)
        
        구성 요소:
        1. 페르소나 프롬프트 (NPC_prompt.json → friendly에 따라 선택)
        2. RAG 컨텍스트 (세계관 지식)
        3. 컨트롤 시그널 (분석 결과)
        4. 출력 제약
        """
        # 페르소나 선택 (JSON 기반)
        persona = self.prompt_loader.build_persona_prompt(self.npc_id, self.state.friendly)
        
        # 컨트롤 시그널
        control_signal = format_control_signal(
            analysis["reason_tags"],
            analysis["friendly_delta"],
            analysis["faith_delta"]
        )
        
        # 시스템 프롬프트 조합: 페르소나 + (RAG 컨텍스트) + 컨트롤 시그널 + 출력 규칙
        system_prompt = persona.strip()
        
        if context:
            system_prompt += "\n\n[WORLD_CONTEXT]\n" + context.strip()
        
        system_prompt += "\n\n" + control_signal.strip()
        
        system_prompt += "\n\n" + (
            "[OUTPUT]\n"
            f"- 한국어로 '{self.korean_name} 대사만' 출력한다.\n"
            "- 선택지/해설/요약/마크다운/코드블록 금지.\n"
            "- 마지막 문장은 (반문/조건 제시/다음 행동 제안) 중 하나로 끝낸다.\n"
        )
        
        return system_prompt.strip()
    
    def chat(
        self,
        user_message: str,
        history: Optional[List[Dict[str, str]]] = None,
        memory_context: Optional[str] = None,
        max_new_tokens: int = 160,
        do_sample: bool = False
    ) -> Dict[str, Any]:
        """
        대화 생성
        
        Args:
            user_message: 사용자 입력
            history: 대화 내역 [{"speaker": "user"|"npc", "content": "..."}, ...]
            memory_context: 로컬에서 검색한 장기 기억 컨텍스트 (Vector DB)
            max_new_tokens: 생성 토큰 수
            do_sample: 샘플링 사용 여부
            
        Returns:
            {
                "npc_response": str,
                "state": Dict[str, int],
                "analysis": Dict[str, Any],
                "debug": Optional[Dict]
            }
        """
        # 1. 의도 분석
        analysis = self.analyzer.analyze(user_message)
        
        # 2. 상태 업데이트
        self.state.apply_delta(
            analysis["friendly_delta"],
            analysis["faith_delta"]
        )
        
        # 3. RAG: 관련 정보 검색 (EC2 로컬 Vector DB)
        context_text = ""
        if self.retriever:
            try:
                search_query = f"{self.npc_id} 성격 특징. {user_message}"
                docs = self.retriever.invoke(search_query)
                context_text = "\n".join([doc.page_content for doc in docs])
            except Exception as e:
                print(f"⚠️ [RAG] 검색 실패: {e}")

        # 4. 장기 기억 컨텍스트 병합 (로컬에서 전달받은 기억)
        if memory_context:
            if context_text:
                context_text = context_text + "\n\n[LONG_TERM_MEMORY]\n" + memory_context
            else:
                context_text = "[LONG_TERM_MEMORY]\n" + memory_context
            print(f"[Memory] 장기 기억 컨텍스트 적용 ({len(memory_context)}자)")

        # 4. 시스템 프롬프트 생성 (JSON 기반 페르소나 + 컨텍스트)
        system_prompt = self._build_system_prompt(user_message, analysis, context=context_text)
        
        # 5. 대화 생성 프롬프트 구성 (Gemma 2 포맷)
        full_prompt = f"<start_of_turn>user\n{system_prompt}<end_of_turn>\n"
        full_prompt += f"<start_of_turn>model\n확인했습니다. {self.korean_name}의 페르소나로 대화하겠습니다.<end_of_turn>\n"
        
        # 대화 이력 추가
        if history:
            for msg in history[-10:]:
                role = "user" if msg.get("speaker") == "user" else "model"
                content = msg.get("content", "")
                full_prompt += f"<start_of_turn>{role}\n{content}<end_of_turn>\n"
        
        # 현재 사용자 메시지 추가
        full_prompt += f"<start_of_turn>user\n{{user_input}}<end_of_turn>\n<start_of_turn>model\n"

        prompt_template = PromptTemplate(input_variables=["user_input"], template=full_prompt)
        chain = prompt_template | self.llm | StrOutputParser()
        raw_response = chain.invoke({"user_input": user_message})
        
        print(f"\n{'='*60}")
        print(f"[DEBUG] LLM 원본 응답:")
        print(raw_response)
        print(f"{'='*60}")
        
        # 6. 후처리
        npc_response = sanitize_npc_response(raw_response)
        
        print(f"[DEBUG] 후처리 결과:")
        print(npc_response)
        print(f"{'='*60}\n")
        
        # 7. 결과 구성
        bucket = get_relationship_bucket(self.state.friendly)
        result = {
            "npc_response": npc_response,
            "state": self.state.to_dict(),
            "analysis": {
                "reason_tags": analysis["reason_tags"],
                "friendly_delta": analysis["friendly_delta"],
                "faith_delta": analysis["faith_delta"],
                "relationship_bucket": bucket
            }
        }
        
        # 디버그 정보
        if self.debug:
            result["debug"] = {
                "raw_response": raw_response,
                "system_prompt": system_prompt,
                "rag_context": context_text,
                "tag_probs": analysis["tag_probs"]
            }
        
        return result


# ============================================================
# 사용 예시
# ============================================================

if __name__ == "__main__":
    import sys
    
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    from app.core.llm_factory import LLMFactory
    
    print("=== NPC Dialogue Pipeline v2 Demo ===\n")
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(os.path.dirname(base_dir), "data")
    ckpt = os.path.join(base_dir, "NPC_model_v2", "best_model.pt")
    thr_json = os.path.join(base_dir, "NPC_model_v2", "thresholds_standard.json")
    prompt_json = os.path.join(data_dir, "NPC_prompt.json")
    
    print("[1/4] Loading IntentAnalyzer (v2)...")
    analyzer = IntentAnalyzer(
        encoder_model="monologg/koelectra-base-v3-discriminator",
        checkpoint_path=ckpt,
        threshold_json_path=thr_json,
        tag_k=3,
        tag_min_p=0.15
    )
    
    print("[2/4] Loading NPC prompts...")
    loader = NPCPromptLoader(prompt_json)
    
    print("[3/4] Loading LLM (via LLMFactory)...")
    llm = LLMFactory.create_llm(model_key="npc")
    
    print("[4/4] Creating pipeline...")
    pipeline = NPCDialoguePipeline(
        analyzer=analyzer,
        llm=llm,
        prompt_loader=loader,
        npc_id="CheongGalchi",
        initial_state=NPCState(friendly=30, faith=30)
    )
    
    pipeline.debug = True
    
    print(f"\n=== {pipeline.korean_name} 대화 시작 ===")
    print("명령어: /debug on|off, /state, exit")
    print()
    
    while True:
        user_input = input("플레이어: ").strip()
        
        if not user_input:
            continue
        
        if user_input.lower() == "exit":
            print("대화를 종료합니다.")
            break
        
        if user_input.startswith("/"):
            if user_input == "/debug on":
                pipeline.debug = True
                print("[CMD] 디버그 모드: ON")
            elif user_input == "/debug off":
                pipeline.debug = False
                print("[CMD] 디버그 모드: OFF")
            elif user_input == "/state":
                print(f"[CMD] 현재 상태: {pipeline.state.to_dict()}")
            else:
                print("[CMD] 알 수 없는 명령어")
            continue
        
        try:
            result = pipeline.chat(user_input)
            
            print(f"\n[{pipeline.korean_name}]")
            print(result["npc_response"])
            print()
            print(f"상태: {result['state']}")
            print(f"분석: 태그={result['analysis']['reason_tags']}, "
                  f"호감={result['analysis']['friendly_delta']:+d}, "
                  f"신뢰={result['analysis']['faith_delta']:+d}, "
                  f"버킷={result['analysis']['relationship_bucket']}")
            
            if pipeline.debug and "debug" in result:
                print(f"\n[디버그]")
                print(f"태그 확률 (상위 5개):")
                top5 = sorted(
                    result["debug"]["tag_probs"].items(),
                    key=lambda x: -x[1]
                )[:5]
                for tag, prob in top5:
                    print(f"  {tag}: {prob:.3f}")
            
            print()
            
        except Exception as e:
            print(f"[오류] {e}")
            if pipeline.debug:
                import traceback
                traceback.print_exc()
