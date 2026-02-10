from typing import Tuple, Optional
import asyncio
import os
import torch
import torch.nn.functional as F
from transformers import BertTokenizer, BertForSequenceClassification
from app.core.config import settings

class GA1Agent:
    """GA1: 유저 입력의 안전성 및 비속어 검증 (가드레일 1단계)"""
    def __init__(self):
        # [경로 자동 보정]
        # 1. 현재 파일(ga1_agent.py)이 있는 폴더 기준 'ga1_model' 경로 계산
        base_dir = os.path.dirname(os.path.abspath(__file__))
        local_model_path = os.path.join(base_dir, "ga1_model")

        # 2. 우선순위: 환경변수(유효할 때) > 로컬 폴더(존재할 때) > HuggingFace Hub ID
        if settings.GA1_MODEL_PATH and os.path.exists(settings.GA1_MODEL_PATH):
            self.model_path = settings.GA1_MODEL_PATH
        elif os.path.exists(local_model_path):
            print(f"📂 [GA1] 로컬 모델 폴더 감지: {local_model_path}")
            self.model_path = local_model_path
        else:
            # 환경변수가 설정되어 있지만 파일이 없거나, 아예 설정이 없는 경우
            # 만약 환경변수가 Hub ID라면 그대로 사용, 아니면 기본 ID 사용
            self.model_path = settings.GA1_MODEL_PATH or "beomi/kcbert-base"
        
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
            if os.path.sep in self.model_path:
                print(f"   👉 (힌트) 로컬 경로 '{self.model_path}'가 정확한지 확인하세요. (현재 실행 위치: {os.getcwd()})")

    async def check_safety(self, message: str) -> Tuple[bool, Optional[str]]:
        """로컬 모델을 사용하여 유저의 입력이 안전한지 검사합니다."""
        if not self.model or not self.tokenizer:
            print("[WARN] GA1 모델이 로드되지 않았습니다. 통과 처리합니다.")
            return True, None

        # [수정] 동기 연산을 수행하는 내부 함수 정의
        def _predict():
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
                    return torch.argmax(logits, dim=-1).item()
            except Exception as e:
                print(f"[ERROR] GA1 추론 중 오류 발생: {e}")
                return None

        try:
            # [수정] 5초 타임아웃 설정: 5초 안에 응답 없으면 TimeoutError 발생
            prediction = await asyncio.wait_for(asyncio.to_thread(_predict), timeout=5.0)
            print(f"[GA1] 입력 안전성 검사 결과: {prediction}")
        except asyncio.TimeoutError:
            print("⚠️ [WARN] GA1 안전성 검사 시간 초과 (5s). 검증을 건너뜁니다.")
            # 타임아웃 시 일단 통과시킴 (서비스 중단 방지)
            return True, None

        if prediction == 1:
            return False, "욕설이나 비속어가 포함되어 있습니다."
        elif prediction == 2:
            return False, "세계관에 어긋나거나 부적절한 표현이 감지되었습니다."
            
        return True, None

ga1_agent = GA1Agent()