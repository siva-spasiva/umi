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

class LLMEngine:
    """실제 LLM(OpenAI, Gemini, Claude 등) 호출 전담 모듈"""
    def __init__(self):
        self.agent = npc_agent
        
        # 파이프라인 생성 (NPC별)
        self.pipelines: Dict[str, NPCDialoguePipeline] = {}
        
        # Vector DB Retriever 가져오기 (RAG용)
        self.retriever = memory_manager.get_retriever(k=2)
        
        print("[LLMEngine] Initialized with pipeline architecture")
    
    def _get_or_create_pipeline(self, npc_id: str) -> NPCDialoguePipeline:
        """NPC별 파이프라인 가져오기 또는 생성"""
        if npc_id not in self.pipelines:
            if not self.agent.generation_enabled:
                raise RuntimeError("대화 생성이 비활성화되어 있습니다.")
            
            # 새 파이프라인 생성
            self.pipelines[npc_id] = NPCDialoguePipeline(
                analyzer=self.agent.analyzer,
                llm=self.agent.llm, 
                retriever=self.retriever, # RAG 검색기 주입
                npc_id=npc_id,
                initial_state=NPCState(friendly=50, faith=50)
            )
        
        return self.pipelines[npc_id]

    @traceable(run_type="llm", name="NPC_Generation")
    async def ask(self, npc_id: str, message: str, history: Optional[List[Dict]] = None) -> str:
        """LLM에게 페르소나와 대화 내역을 전달하여 응답을 생성합니다."""
        # GPU Proxy 모드: AWS EC2 GPU 서버에 위임
        if settings.USE_GPU_PROXY:
            from app.core.gpu_proxy import gpu_proxy
            return await gpu_proxy.generate_npc_response(npc_id, message, history)

        try:
            # 파이프라인 가져오기
            pipeline = self._get_or_create_pipeline(npc_id)
            
            # 대화 생성 (비동기 래핑)
            result = await asyncio.to_thread(
                pipeline.chat,
                message,
                max_new_tokens=160,
                do_sample=False
            )
            
            # 응답 반환
            response = result["npc_response"]
            
            # 상태 변화 로깅
            analysis = result["analysis"]
            print(f"[LLMEngine] {npc_id} 응답 완료")
            print(f"  - 호감도: {result['state']['friendly']} ({analysis['friendly_delta']:+d})")
            print(f"  - 신뢰도: {result['state']['faith']} ({analysis['faith_delta']:+d})")
            print(f"  - 태그: {', '.join(analysis['reason_tags']) or 'NONE'}")
            
            return response
            
        except asyncio.TimeoutError:
            print(f"⚠️ [WARN] LLM({npc_id}) 응답 시간 초과 (300s).")
            return "시스템: (응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.)"
        except Exception as e:
            print(f"⚠️ [ERROR] LLM 생성 중 오류: {e}")
            return "시스템: (오류가 발생했습니다.)"
    
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
            
    async def save_long_term_memory(self, npc_id: str, history: List[Dict]):
        """
        [장기 기억 형성 프로세스]
        1. 대화 로그(history)를 StoryAgent에게 전달하여 요약(일기) 생성
        2. 요약된 내용을 Vector DB에 저장
        """
        print(f"[Memory] {npc_id}의 기억을 생성합니다...")
        
        # 1. 요약 생성 (StoryAgent 활용)
        # history는 [{"role": "user", "content": "..."}, ...] 형태의 리스트를 문자열로 변환
        summary = story_agent.generate_diary(str(history), fish_level=0)
        
        # 2. Vector DB 저장
        memory_manager.add_memory(
            text=summary,
            metadata={"npc_id": npc_id, "type": "diary"}
        )

llm_engine = LLMEngine()