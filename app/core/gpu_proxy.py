"""
GPU Proxy Client
- 로컬 Mac에서 AWS EC2 GPU Inference Server에 HTTP 요청을 보내는 클라이언트
- USE_GPU_PROXY=true 일 때 각 Agent에서 이 모듈을 통해 원격 추론 수행
"""

import httpx
from typing import Tuple, Optional, List, Dict


class GPUProxyClient:
    """AWS EC2 GPU Inference Server와 통신하는 비동기 HTTP 클라이언트"""

    def __init__(self):
        # 설정은 첫 호출 시 lazy-load (순환 import 방지)
        self._client: Optional[httpx.AsyncClient] = None
        self._server_url: Optional[str] = None
        self._timeout: int = 60

    def _get_config(self):
        """설정 lazy-load"""
        if self._server_url is None:
            from app.core.config import settings
            self._server_url = settings.GPU_SERVER_URL.rstrip("/")
            self._timeout = settings.GPU_PROXY_TIMEOUT
        return self._server_url, self._timeout

    async def _get_client(self) -> httpx.AsyncClient:
        """httpx 클라이언트 lazy 생성"""
        if self._client is None or self._client.is_closed:
            server_url, timeout = self._get_config()
            self._client = httpx.AsyncClient(
                base_url=server_url,
                timeout=httpx.Timeout(timeout, connect=10.0)
            )
        return self._client

    # ============================================================
    # GA1: 안전성 검사
    # ============================================================

    async def check_safety(self, message: str) -> Tuple[bool, Optional[str]]:
        """
        GA1 안전성 검사를 GPU 서버에 위임

        Returns:
            (is_safe, reason) 튜플
        """
        try:
            client = await self._get_client()
            response = await client.post("/infer/ga1", json={"message": message})
            response.raise_for_status()

            data = response.json()
            return data["is_safe"], data.get("reason")

        except httpx.ConnectError:
            print("⚠️ [GPUProxy] GA1: GPU 서버에 연결할 수 없습니다. 안전 통과 처리합니다.")
            return True, None
        except Exception as e:
            print(f"⚠️ [GPUProxy] GA1 오류: {e}. 안전 통과 처리합니다.")
            return True, None

    # ============================================================
    # NPC: 대화 생성
    # ============================================================

    async def generate_npc_response(
        self,
        npc_id: str,
        message: str,
        history: Optional[List[Dict]] = None,
        memory_context: Optional[str] = None
    ) -> Dict:
        """
        NPC 대화 생성을 GPU 서버에 위임

        Returns:
            {
                "response": str,        # NPC 응답 텍스트
                "analysis": Dict,       # 의도 분석 결과 (friendly_delta, faith_delta, reason_tags 등)
                "state": Dict           # 현재 NPC 상태 (friendly, faith)
            }
        """
        try:
            client = await self._get_client()
            payload = {
                "npc_id": npc_id,
                "message": message,
                "history": history,
                "memory_context": memory_context
            }
            response = await client.post("/infer/npc", json=payload)
            response.raise_for_status()

            data = response.json()

            # 상태 변화 로깅
            analysis = data.get("analysis", {})
            state = data.get("state", {})
            if analysis:
                print(f"[GPUProxy] {npc_id} 응답 완료 (Remote GPU)")
                print(f"  - 호감도: {state.get('friendly', '?')} ({analysis.get('friendly_delta', 0):+d})")
                print(f"  - 신뢰도: {state.get('faith', '?')} ({analysis.get('faith_delta', 0):+d})")
                tags = analysis.get('reason_tags', [])
                print(f"  - 태그: {', '.join(tags) if tags else 'NONE'}")

            return {
                "response": data.get("response", ""),
                "analysis": analysis,
                "state": state
            }

        except httpx.ConnectError:
            print("⚠️ [GPUProxy] NPC: GPU 서버에 연결할 수 없습니다.")
            return {
                "response": "시스템: (GPU 서버에 연결할 수 없습니다. 서버 상태를 확인해주세요.)",
                "analysis": {},
                "state": {}
            }
        except Exception as e:
            print(f"⚠️ [GPUProxy] NPC 오류: {e}")
            return {
                "response": "시스템: (원격 추론 중 오류가 발생했습니다.)",
                "analysis": {},
                "state": {}
            }

    # ============================================================
    # Story: 텍스트/일기 생성
    # ============================================================

    async def generate_story(self, prompt: str, max_new_tokens: int = 256) -> str:
        """
        Story 텍스트 생성을 GPU 서버에 위임

        Returns:
            생성된 텍스트
        """
        try:
            client = await self._get_client()
            payload = {
                "prompt": prompt,
                "max_new_tokens": max_new_tokens
            }
            response = await client.post("/infer/story", json=payload)
            response.raise_for_status()

            return response.json()["text"]

        except httpx.ConnectError:
            print("⚠️ [GPUProxy] Story: GPU 서버에 연결할 수 없습니다.")
            return "시스템: GPU 서버에 연결할 수 없습니다."
        except Exception as e:
            print(f"⚠️ [GPUProxy] Story 오류: {e}")
            return "시스템: 원격 추론 중 오류가 발생했습니다."

    async def generate_diary(
        self,
        messages: str,
        fish_level: int = 3,
        max_new_tokens: int = 400
    ) -> str:
        """
        Story 일기 생성을 GPU 서버에 위임

        Returns:
            생성된 일기 텍스트
        """
        try:
            client = await self._get_client()
            payload = {
                "messages": messages,
                "fish_level": fish_level,
                "max_new_tokens": max_new_tokens
            }
            response = await client.post("/infer/story/diary", json=payload)
            response.raise_for_status()

            return response.json()["text"]

        except httpx.ConnectError:
            print("⚠️ [GPUProxy] Diary: GPU 서버에 연결할 수 없습니다.")
            return "시스템: GPU 서버에 연결할 수 없습니다."
        except Exception as e:
            print(f"⚠️ [GPUProxy] Diary 오류: {e}")
            return "시스템: 원격 추론 중 오류가 발생했습니다."



    # ============================================================
    # NPC 대화(Conversation): 다중 NPC 대화 생성
    # ============================================================

    async def generate_npc_conversation(
        self,
        topic: str,
        npc_ids: List[str],
        include_user: bool = False,
        user_message: Optional[str] = None,
        num_turns: int = 5,
        history: Optional[List[Dict]] = None
    ) -> Dict:
        """
        NPC 대화 생성을 GPU 서버에 위임

        Args:
            topic: 대화 주제
            npc_ids: 참여 NPC ID 목록
            include_user: 유저 참여 여부
            user_message: 유저 참여 시 유저 발언
            num_turns: NPC-only 모드 턴 수
            history: 이전 대화 내역

        Returns:
            {"topic": str, "turns": List[Dict], "npc_states": Dict}
        """
        try:
            client = await self._get_client()
            payload = {
                "topic": topic,
                "npc_ids": npc_ids,
                "include_user": include_user,
                "user_message": user_message,
                "num_turns": num_turns,
                "history": history
            }
            response = await client.post("/infer/npc/conversation", json=payload)
            response.raise_for_status()

            data = response.json()
            print(f"[GPUProxy] NPC 대화 완료 (Remote GPU): {len(data.get('turns', []))} turns")
            return data

        except httpx.ConnectError:
            print("⚠️ [GPUProxy] Conversation: GPU 서버에 연결할 수 없습니다.")
            return {
                "topic": topic,
                "turns": [{"speaker": "system", "speaker_id": "system",
                           "content": "GPU 서버에 연결할 수 없습니다.", "analysis": None}],
                "npc_states": {}
            }
        except Exception as e:
            print(f"⚠️ [GPUProxy] Conversation 오류: {e}")
            return {
                "topic": topic,
                "turns": [{"speaker": "system", "speaker_id": "system",
                           "content": f"원격 추론 중 오류: {e}", "analysis": None}],
                "npc_states": {}
            }

    # ============================================================
    # 유틸리티
    # ============================================================

    async def health_check(self) -> dict:
        """GPU 서버 상태 확인"""
        try:
            client = await self._get_client()
            response = await client.get("/health")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}

    async def close(self):
        """클라이언트 종료"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# 싱글톤 인스턴스
gpu_proxy = GPUProxyClient()
