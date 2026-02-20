import os
import asyncio
from typing import List, Dict, Optional
from app.agents.npc_agent import npc_agent
from app.agents.npc_pipeline import NPCDialoguePipeline
from app.agents.npc_dialogue_engine import NPCState
from app.core.config import settings
from langsmith import traceable

# 메모리 및 스토리 에이전트 추가
from app.core.memory import memory_manager
from app.agents.story_agent import story_agent
from app.core.database import db
from datetime import datetime

# 감정 변화 즉시 기억 트리거 임계값
EMOTION_TRIGGER_THRESHOLD = 3


class LLMEngine:
    """실제 LLM(OpenAI, Gemini, Claude 등) 호출 전담 모듈"""
    def __init__(self):
        self.agent = npc_agent
        
        # 파이프라인 생성 (NPC별)
        self.pipelines: Dict[str, NPCDialoguePipeline] = {}
        
        # Vector DB Retriever 가져오기 (RAG용)
        self.retriever = memory_manager.get_retriever(k=2)
        
        # NPC별 세션 버퍼: {npc_id: [{"speaker": ..., "content": ..., "analysis": ...}, ...]}
        self.session_buffers: Dict[str, List[Dict]] = {}
        
        # 전역 NPCPromptLoader 초기화 (NPC 목록 및 초기 스탯 로드용)
        try:
            from app.agents.npc_pipeline import NPCPromptLoader
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            char_json_path = os.path.join(base_dir, "data", "characters.json")
            prompt_json_path = os.path.join(base_dir, "data", "NPC_prompt.json")
            self.loader = NPCPromptLoader(prompt_json_path, char_json_path)
            print(f"[LLMEngine] Global NPCPromptLoader initialized. Available NPCs: {self.loader.get_all_npc_ids()}")
        except Exception as e:
            print(f"⚠️ [LLMEngine] Failed to init NPCPromptLoader in __init__: {e}")
            self.loader = None
        
        print("[LLMEngine] Initialized with pipeline architecture")
    
    def _get_or_create_pipeline(self, npc_id: str) -> NPCDialoguePipeline:
        """NPC별 파이프라인 가져오기 또는 생성"""
        if npc_id not in self.pipelines:
            if not self.agent.generation_enabled:
                raise RuntimeError("대화 생성이 비활성화되어 있습니다.")
            
            # Use self.loader if available, else recreate (fallback)
            loader = self.loader
            if not loader:
                # Fallback: create new loader if init failed
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                char_json_path = os.path.join(base_dir, "data", "characters.json")
                prompt_json_path = os.path.join(base_dir, "data", "NPC_prompt.json")
                
                from app.agents.npc_pipeline import NPCPromptLoader
                loader = NPCPromptLoader(prompt_json_path, char_json_path)

            # 초기 상태 로드
            initial_state = loader.get_initial_state(npc_id)
            print(f"[LLMEngine] {npc_id} 초기 상태: {initial_state}")

            # 새 파이프라인 생성
            self.pipelines[npc_id] = NPCDialoguePipeline(
                analyzer=self.agent.analyzer,
                llm=self.agent.llm, 
                retriever=self.retriever, # RAG 검색기 주입
                npc_id=npc_id,
                prompt_loader=loader,  # 로더 주입
                initial_state=initial_state
            )
        
        return self.pipelines[npc_id]

    @traceable(run_type="llm", name="NPC_Generation")
    async def ask(
        self, 
        npc_id: str, 
        message: str, 
        history: Optional[List[Dict]] = None,
        update_state: bool = True,
        forced_state: Optional[Dict] = None
    ) -> Dict:
        """
        LLM에게 페르소나와 대화 내역을 전달하여 응답을 생성합니다.
        
        Args:
            npc_id: NPC ID
            message: 유저 메시지 또는 시스템 프롬프트
            history: 대화 내역
            update_state: 상태 업데이트 여부 (True: 업데이트 함, False: 안함)
            forced_state: 강제 상태 설정 (None이면 현재 상태 사용)

        Returns:
            {
                "response": str,
                "analysis": Dict,
                "state": Dict
            }
        """
        # GPU Proxy 모드: AWS EC2 GPU 서버에 위임
        if settings.USE_GPU_PROXY:
            from app.core.gpu_proxy import gpu_proxy
            
            # 로컬 ChromaDB에서 장기 기억 검색
            memory_context = self._retrieve_memory_context(npc_id, message)
            
            result = await gpu_proxy.generate_npc_response(
                npc_id, message, history,
                memory_context=memory_context,
                update_state=update_state,
                forced_state=forced_state
            )
        else:
            try:
                # 파이프라인 가져오기
                pipeline = self._get_or_create_pipeline(npc_id)
                
                # 대화 생성 (비동기 래핑)
                raw_result = await asyncio.to_thread(
                    pipeline.chat,
                    message,
                    max_new_tokens=160,
                    do_sample=False,
                    update_state=update_state,
                    forced_state=forced_state
                )
                
                result = {
                    "response": raw_result["npc_response"],
                    "analysis": raw_result.get("analysis", {}),
                    "state": raw_result.get("state", {})
                }
                
                # 로깅
                analysis = result["analysis"]
                print(f"[LLMEngine] {npc_id} 응답 완료")
                print(f"  - 호감도: {result['state'].get('friendly', '?')} ({analysis.get('friendly_delta', 0):+d})")
                print(f"  - 신뢰도: {result['state'].get('faith', '?')} ({analysis.get('faith_delta', 0):+d})")
                print(f"  - 태그: {', '.join(analysis.get('reason_tags', [])) or 'NONE'}")
                
            except asyncio.TimeoutError:
                print(f"⚠️ [WARN] LLM({npc_id}) 응답 시간 초과 (300s).")
                return {
                    "response": "시스템: (응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.)",
                    "analysis": {},
                    "state": {}
                }
            except Exception as e:
                print(f"⚠️ [ERROR] LLM 생성 중 오류: {e}")
                return {
                    "response": "시스템: (오류가 발생했습니다.)",
                    "analysis": {},
                    "state": {}
                }

        # ── 장기 기억 처리 ──────────────────────────────────
        analysis = result.get("analysis", {})
        npc_response = result.get("response", "")

        # 세션 버퍼에 대화 누적
        self._append_to_session(npc_id, message, npc_response, analysis)

        return result
    
    # ================================================================
    # 장기 기억 관련 메서드
    # ================================================================

    def _retrieve_memory_context(self, npc_id: str, message: str) -> Optional[str]:
        """
        로컬 ChromaDB에서 현재 대화와 관련된 장기 기억을 검색.
        검색된 기억을 문자열로 반환하여 GPU 서버에 전달.
        """
        try:
            retriever = memory_manager.get_retriever(k=3)
            search_query = f"{npc_id} {message}"
            docs = retriever.invoke(search_query)
            
            if not docs:
                return None
            
            memory_texts = [doc.page_content for doc in docs]
            combined = "\n---\n".join(memory_texts)
            print(f"[Memory] 장기 기억 {len(docs)}건 검색됨 ({npc_id})")
            for i, doc in enumerate(docs):
                meta = doc.metadata
                print(f"  [{i+1}] type={meta.get('memory_type', 'unknown')}, "
                      f"npc={meta.get('npc_id', '?')}, "
                      f"len={len(doc.page_content)}자")
            
            return combined
            
        except Exception as e:
            print(f"⚠️ [Memory] 장기 기억 검색 실패: {e}")
            return None

    def _append_to_session(self, npc_id: str, user_msg: str, npc_response: str, analysis: Dict):
        """대화 턴을 세션 버퍼에 추가"""
        if npc_id not in self.session_buffers:
            self.session_buffers[npc_id] = []
        
        self.session_buffers[npc_id].append({
            "user": user_msg,
            "npc": npc_response,
            "friendly_delta": analysis.get("friendly_delta", 0),
            "faith_delta": analysis.get("faith_delta", 0),
            "tags": analysis.get("reason_tags", [])
        })
        
        buffer_size = len(self.session_buffers[npc_id])
        print(f"[Memory] 세션 버퍼 ({npc_id}): {buffer_size}턴 누적")

    # [REMOVED] _save_emotion_triggered_memory

    async def save_session_summary(self, day_index: int, npc_id: Optional[str] = None, user_id: str = None) -> Dict[str, str]:
        """
        세션 종료 시 버퍼의 대화를 요약하여:
        1. Vector DB에 저장 (장기 기억용 - session_summary)
        2. MongoDB 'day_summaries' 컬렉션에 저장 (모니터링용)
        
        Args:
            day_index: 게임 내 일차 (1~7 등)
            npc_id: NPC 식별자 (None이면 버퍼가 있는 모든 NPC에 대해 수행)
            user_id: 유저 식별자 (모니터링 저장용 필수)
            
        Returns:
            {npc_id: summary_text, ...}
        """
        if npc_id:
            target_ids = [npc_id]
        else:
            # npc_id가 없으면 로더에서 전체 NPC 목록을 가져옴 (characters.json 기준)
            if self.loader:
                target_ids = self.loader.get_all_npc_ids()
                print(f"[Memory] 모든 NPC({len(target_ids)}명)에 대해 세션 요약 진행")
            else:
                target_ids = list(self.session_buffers.keys())
                
        summaries: Dict[str, str] = {}
        
        for target_id in target_ids:
            buffer = self.session_buffers.get(target_id, [])
            
            if not buffer:
                # 버퍼가 비어있으면 스킵
                continue
            
            print(f"[Memory] {target_id}의 Day {day_index} 세션 요약 생성 중... ({len(buffer)}턴)")
            
            # 세션 버퍼를 대화 형태로 변환
            conversation_text = ""
            for turn in buffer:
                conversation_text += f"플레이어: {turn['user']}\n"
                conversation_text += f"NPC({target_id}): {turn['npc']}\n"
                conversation_text += f"  [감정: 호감도 {turn['friendly_delta']:+d}, 신뢰도 {turn['faith_delta']:+d}]\n\n"
            
            # StoryAgent로 요약 생성 (GPU Proxy 모드에서는 원격 호출)
            try:
                if settings.USE_GPU_PROXY:
                    from app.core.gpu_proxy import gpu_proxy
                    summary = await gpu_proxy.generate_diary(
                        messages=conversation_text,
                        fish_level=0,
                        max_new_tokens=400
                    )
                else:
                    summary = await asyncio.to_thread(
                        story_agent.generate_diary,
                        conversation_text,
                        fish_level=0
                    )
            except Exception as e:
                print(f"⚠️ [Memory] 세션 요약 생성 실패 ({target_id}): {e}")
                # 폴백: 요약 없이 핵심 대화만 저장
                summary = f"Day {day_index} 세션 - {target_id}와 {len(buffer)}턴 대화. {conversation_text[:200]}..."
            
            # 1. Vector DB에 저장 (Memory)
            memory_manager.add_memory(
                text=summary,
                metadata={
                    "npc_id": target_id,
                    "memory_type": "session_summary", # Changed from day_summary
                    "day_index": day_index,
                    "turn_count": len(buffer)
                }
            )
            
            # 2. MongoDB에 저장 (Log/Monitoring)
            if user_id:
                try:
                    await db["day_summaries"].insert_one({
                        "user_id": user_id,
                        "day_index": day_index,
                        "npc_id": target_id,
                        "summary": summary,
                        "full_conversation": conversation_text, # 전체 대화도 백업
                        "timestamp": datetime.utcnow()
                    })
                    print(f"✅ [DB] Day Summary 저장 완료 ({target_id})")
                except Exception as e:
                    print(f"⚠️ [DB] Day Summary 저장 실패: {e}")

            print(f"🧠 [Memory] Day {day_index} 세션 요약 처리 완료 ({target_id}, {len(buffer)}턴)")
            
            # 세션 버퍼 초기화
            self.session_buffers[target_id] = []
            
            summaries[target_id] = summary
            
        return summaries

    def get_session_buffer(self, npc_id: str) -> List[Dict]:
        """세션 버퍼 조회 (디버그용)"""
        return self.session_buffers.get(npc_id, [])
    
    # ================================================================
    # 기존 유틸리티 메서드
    # ================================================================

    def get_npc_state(self, npc_id: str) -> Optional[Dict]:
        """NPC 현재 상태 조회"""
        if npc_id in self.pipelines:
            return self.pipelines[npc_id].state.to_dict()
        return None
    
    def reset_npc_state(self, npc_id: str):
        """NPC 상태 초기화"""
        if npc_id in self.pipelines:
            self.pipelines[npc_id].state = NPCState(friendly=50, faith=50)
            print(f"[LLMEngine] {npc_id} 상태 초기화")

    def set_npc_state(self, npc_id: str, friendly: int, faith: int):
        """NPC 상태 강제 설정 (Debug용)"""
        try:
            # 강제로 생성 활성화 (잠시)
            original_enabled = self.agent.generation_enabled
            self.agent.generation_enabled = True
            
            # 파이프라인이 없으면 생성
            _ = self._get_or_create_pipeline(npc_id)
            
            # 원복
            self.agent.generation_enabled = original_enabled
            
            if npc_id in self.pipelines:
                self.pipelines[npc_id].state.friendly = friendly
                self.pipelines[npc_id].state.faith = faith
                print(f"[LLMEngine] {npc_id} 상태 강제 설정: Friendly={friendly}, Faith={faith}")
            else:
                print(f"⚠️ [LLMEngine] {npc_id} 파이프라인 생성 실패, 상태 설정 불가")
        except Exception as e:
            print(f"⚠️ [LLMEngine] set_npc_state 중 오류: {e}")
            # 에러를 다시 던지지 않고 로그만 남김 (테스트 중단 방지)
            
    async def save_long_term_memory(self, npc_id: str, history: List[Dict]):
        """
        [레거시] 장기 기억 형성 프로세스 — save_session_summary 사용 권장
        1. 대화 로그(history)를 StoryAgent에게 전달하여 요약(일기) 생성
        2. 요약된 내용을 Vector DB에 저장
        """
        print(f"[Memory] {npc_id}의 기억을 생성합니다...")
        
        summary = story_agent.generate_diary(str(history), fish_level=0)
        
        memory_manager.add_memory(
            text=summary,
            metadata={"npc_id": npc_id, "memory_type": "diary"}
        )

llm_engine = LLMEngine()