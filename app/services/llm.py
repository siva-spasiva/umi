from typing import Dict, Any

class LLMAgent:
    """
    실제 LLM(OpenAI, Gemini 등)과의 통신을 담당하는 에이전트
    """
    def __init__(self):
        # API_KEY 설정 등을 여기서 수행
        pass

    async def generate_response(self, user_id: str, npc_id: str, message: str, context: list) -> str:
        """
        LLM에게 메시지를 전달하고 응답을 생성합니다.
        """
        # 실제 구현 시에는 여기서 외부 API를 호출합니다.
        return f"바다의 파동이 {npc_id}(으)로서 당신의 말('{message}')을 기억할 것입니다."

llm_agent = LLMAgent()