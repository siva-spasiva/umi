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

# Singleton instance
word_masker = WordMasker()
