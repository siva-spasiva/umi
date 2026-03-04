from typing import List, Dict

class LLMEngine:
    """실제 LLM(OpenAI, Gemini, Claude 등) 호출 전담 모듈"""
    def __init__(self):
        # TODO: 외부 API 클라이언트를 여기서 초기화하세요.
        pass

    async def ask(self, npc_id: str, message: str, history: List[Dict]) -> str:
        """LLM에게 페르소나와 대화 내역을 전달하여 응답을 생성합니다."""
        # TODO: 실제 LLM 호출 로직을 구현하세요.
        return f"[{npc_id}] 바다의 흐름이 당신의 말 '{message}'에 응답하고 있습니다."

llm_engine = LLMEngine()