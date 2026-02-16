import json
import os
from typing import List

class WordMasker:
    def __init__(self):
        self.forbidden_words: List[str] = self._load_forbidden_words()

    def _load_forbidden_words(self) -> List[str]:
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            data_path = os.path.join(base_dir, "data/word_dictinary.json")
            if not os.path.exists(data_path):
                print(f"⚠️ [WordMasker] Dictionary file not found at: {data_path}")
                return []
                
            with open(data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ [WordMasker] Failed to load forbidden words: {e}")
            return []

    def mask_text(self, text: str) -> str:
        if not text:
            return ""
        
        masked_text = text
        for word in self.forbidden_words:
            if word in masked_text:
                masked_text = masked_text.replace(word, "뻐끔")
        return masked_text

    def mask_randomly(self, text: str, ratio: float = 0.8) -> str:
        """
        텍스트의 단어 중 일정 비율(ratio)을 무작위로 '뻐끔'으로 치환
        (단, 이미 '뻐끔'인 것은 유지)
        """
        if not text:
            return ""

        import random
        
        # 공백 기준으로 분리
        words = text.split()
        masked_words = []
        
        for word in words:
            # 이미 마스킹된 단어('뻐끔' 포함)는 건너뛰기
            if "뻐끔" in word:
                masked_words.append(word)
                continue
                
            # 확률적으로 마스킹
            if random.random() < ratio:
                masked_words.append("뻐끔")
            else:
                masked_words.append(word)
                
        return " ".join(masked_words)

# Singleton instance
word_masker = WordMasker()
