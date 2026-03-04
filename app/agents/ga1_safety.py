from typing import Tuple, Optional
import os
import torch
import torch.nn.functional as F
from transformers import BertTokenizer, BertForSequenceClassification

class GA1SafetyAgent:
    """GA1: 유저 입력의 안전성 및 비속어 검증 (가드레일 1단계)"""
    def __init__(self):
        # 모델 경로 설정 (AWS 서버 내 경로 또는 HuggingFace Hub ID)
        # 예: "beomi/kcbert-base" 또는 로컬 경로 "./models/ga1_model"
        self.model_path = "beomi/kcbert-base" 
        
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.tokenizer = None
        
        self._load_model()

    def _load_model(self):
        """서버 시작 시 모델을 메모리에 로드합니다."""
        try:
            print(f"🔄 [GA1] Loading Safety Model from {self.model_path}...")
            self.tokenizer = BertTokenizer.from_pretrained(self.model_path)
            self.model = BertForSequenceClassification.from_pretrained(self.model_path)
            self.model.to(self.device)
            self.model.eval()
            print(f"✅ [GA1] Model Loaded on {self.device}")
        except Exception as e:
            print(f"⚠️ [GA1] 모델 로드 실패: {e}")

    async def check_safety(self, message: str) -> Tuple[bool, Optional[str]]:
        """로컬 모델을 사용하여 유저의 입력이 안전한지 검사합니다."""
        if not self.model or not self.tokenizer:
            print("[WARN] GA1 모델이 로드되지 않았습니다. 통과 처리합니다.")
            return True, None

        try:
            inputs = self.tokenizer(
                message,
                return_tensors="pt",
                truncation=True,
                padding=True,
                max_length=128
            ).to(self.device)

            with torch.no_grad():
                logits = self.model(**inputs).logits
                prediction = torch.argmax(logits, dim=-1).item()
            
            # 학습된 라벨에 따라 수정 필요 (여기서는 1을 부적절로 가정)
            if prediction == 1:
                return False, "세계관에 어긋나거나 부적절한 표현이 감지되었습니다."

        except Exception as e:
            print(f"[ERROR] GA1 추론 중 오류 발생: {e}")
            # 오류 발생 시 안전하다고 가정하거나 차단할 수 있음 (여기선 통과)

        return True, None

ga1_safety = GA1SafetyAgent()