import re
from typing import Tuple, Optional, List

class GuardrailAgent:
    """
    GA(Guardrail Agent): 유저의 입력과 LLM의 출력을 검증하는 전담 에이전트
    """
    def __init__(self):
        # 세계관에 어긋나는 금지어 설정
        self.banned_words = ["범고래", "숭배", "노예", "납치"]
        self.system_patterns = ["AI 모델로서", "도와드릴 수 없습니다", "가이드라인에 따라"]

    async def validate_input(self, message: str) -> Tuple[bool, Optional[str]]:
        """입력 검증: 부적절한 질문 차단"""
        # 1. 금지어 체크
        for word in self.banned_words:
            if word in message:
                return False, f"부적절한 단어('{word}')가 포함되어 있습니다."

        # 2. 입력 길이 체크
        if len(message.strip()) < 2:
            return False, "내용이 너무 짧습니다. 조금 더 자세히 말씀해 주세요."

        # 3. 비정상 패턴 (특수문자 도배 등)
        if re.search(r'([^a-zA-Z0-9가-힣\s])\1{4,}', message):
            return False, "비정상적인 입력이 감지되었습니다."

        return True, None

    async def validate_output(self, response: str) -> Tuple[bool, str]:
        """출력 검증: 페르소나 이탈 방지"""
        for pattern in self.system_patterns:
            if pattern in response:
                return False, "바다의 기운이 불안정하여 대답하기 어렵군요. 다시 말씀해 주시겠어요?"
        
        return True, response

ga_agent = GuardrailAgent()