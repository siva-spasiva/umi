from typing import List, Tuple, Optional
import re

class GuardrailService:
    # 세계관에 어긋나거나 부적절한 금지어 설정
    BANNED_WORDS = ["범고래", "숭배", "노예", "납치"]

    def __init__(self):
        pass

    async def validate_input(self, message: str) -> Tuple[bool, Optional[str]]:
        """
        유저의 입력을 LLM에 전달하기 전에 검증합니다.
        반환값: (통과 여부, 에러 메시지)
        """
        # 1. 금지어 체크
        for word in self.BANNED_WORDS:
            if word in message:
                return False, f"부적절한 단어('{word}')가 포함되어 있습니다."

        # 2. 너무 짧거나 의미 없는 입력 체크
        if len(message.strip()) < 2:
            return False, "조금 더 자세하게 말씀해 주세요."

        # 3. 특수문자 도배 등 패턴 체크
        if re.search(r'([^a-zA-Z0-9가-힣\s])\1{4,}', message):
            return False, "비정상적인 입력 패턴이 감지되었습니다."

        return True, None

    async def validate_output(self, response: str) -> Tuple[bool, str]:
        """
        LLM의 응답이 페르소나를 유지하는지, 혹은 부적절한 내용을 담고 있는지 검증합니다.
        반환값: (통과 여부, 수정된 응답)
        """
        # 출력 가드레일 예시: LLM이 갑자기 AI임을 밝히거나 시스템 메시지를 노출하는 경우 필터링
        system_patterns = ["AI 모델로서", "도와드릴 수 없습니다", "가이드라인에 따라"]
        
        for pattern in system_patterns:
            if pattern in response:
                return False, "죄송합니다. 바다의 기운이 불안정하여 다시 말씀해 주시겠어요?"

        return True, response

guardrail_service = GuardrailService()