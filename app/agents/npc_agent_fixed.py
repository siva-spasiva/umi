import os
import torch
import torch.nn as nn
from transformers import AutoModel, AutoTokenizer

# 학습 시 정의한 것과 동일한 모델 구조
class UmiJudger(nn.Module):
    def __init__(self, model_name="monologg/koelectra-base-v3-discriminator", num_tags=12):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(model_name)
        hidden_size = self.encoder.config.hidden_size
        self.dropout = nn.Dropout(0.1)
        self.tag_head = nn.Linear(hidden_size, num_tags)
        self.friendly_head = nn.Linear(hidden_size, 11)
        self.faith_head = nn.Linear(hidden_size, 11)

    def forward(self, input_ids, attention_mask):
        outputs = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        cls_output = outputs.last_hidden_state[:, 0, :]
        cls_output = self.dropout(cls_output)
        return (
            self.tag_head(cls_output),
            self.friendly_head(cls_output),
            self.faith_head(cls_output),
        )


class NpcAgent:
    """
    학습된 UmiJudger 모델을 사용하여 대화의 의도와 스탯 변화를 예측합니다.
    """
    def __init__(self):
        self.model_name = "monologg/koelectra-base-v3-discriminator"
        
        # 경로 자동 보정
        base_dir = os.path.dirname(os.path.abspath(__file__))
        local_model_path = os.path.join(base_dir, "NPC_model")
        
        if os.path.exists(local_model_path):
            self.model_path = local_model_path
            print(f"📂 [NpcAgent] 로컬 모델 폴더 감지: {local_model_path}")
        else:
            self.model_path = None
            print(f"⚠️ [NpcAgent] NPC_model 폴더를 찾을 수 없습니다. 베이스 모델만 사용합니다.")
        
        # 디바이스 설정
        if torch.cuda.is_available():
            self.device = "cuda"
        elif torch.backends.mps.is_available():
            self.device = "mps"
        else:
            self.device = "cpu"
        
        self.model = None
        self.tokenizer = None
        self._load_model()
    
    def _load_model(self):
        """학습된 UmiJudger 모델을 로드합니다."""
        try:
            print(f"🔄 [NpcAgent] Loading Tokenizer: {self.model_name}...")
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            
            print(f"🔄 [NpcAgent] Loading UmiJudger Model...")
            self.model = UmiJudger(model_name=self.model_name)
            
            # 학습된 가중치 로드
            if self.model_path:
                best_model_path = os.path.join(self.model_path, "best_model.pt")
                if os.path.exists(best_model_path):
                    print(f"🔄 [NpcAgent] Loading trained weights from: {best_model_path}")
                    state_dict = torch.load(best_model_path, map_location=self.device)
                    self.model.load_state_dict(state_dict)
                    print(f"✅ [NpcAgent] Trained weights loaded successfully")
                else:
                    print(f"⚠️ [NpcAgent] 'best_model.pt' not found. Using base model.")
            
            self.model.to(self.device)
            self.model.eval()
            print(f"✅ [NpcAgent] Model Ready on {self.device}")
            
        except Exception as e:
            print(f"⚠️ [NpcAgent] 모델 로드 실패: {e}")
    
    def predict(self, text: str, tag_threshold: float = 0.5) -> dict:
        """
        텍스트를 입력받아 태그, friendly/faith 변화를 예측합니다.
        
        Args:
            text: 입력 텍스트 (예: "SPEAKER:user\nTARGET:umi\nFRIENDLY:50\nFAITH:60\n[msg] 안녕?")
            tag_threshold: 태그 임계값
            
        Returns:
            {
                "pred_tags": [태그 리스트],
                "tag_probs": {태그: 확률},
                "friendly_delta": int,
                "faith_delta": int,
                "friendly_prob": float,
                "faith_prob": float
            }
        """
        if not self.model or not self.tokenizer:
            return {"error": "모델이 로드되지 않았습니다."}
        
        try:
            # 토크나이징
            encoding = self.tokenizer(
                text,
                max_length=256,
                padding="max_length",
                truncation=True,
                return_tensors="pt"
            )
            
            input_ids = encoding["input_ids"].to(self.device)
            attention_mask = encoding["attention_mask"].to(self.device)
            
            # 예측
            with torch.no_grad():
                tag_logits, friendly_logits, faith_logits = self.model(input_ids, attention_mask)
            
            # 태그 예측 (multi-label)
            VALID_TAGS = [
                "MAINTAIN_FAITH", "SHAKE_FAITH", "PROTECT_DOCTRINE",
                "PROTECT_SECRET", "INCREASE_SUSPICION", "REDUCE_SUSPICION",
                "DEFLECT", "GASLIGHT", "TEST_BOUNDARY",
                "BUILD_TRUST", "WITHDRAW_TRUST", "OPPORTUNISTIC"
            ]
            
            tag_probs = torch.sigmoid(tag_logits[0]).cpu().numpy()
            pred_tags = [VALID_TAGS[i] for i, p in enumerate(tag_probs) if p >= tag_threshold]
            tag_probs_dict = {VALID_TAGS[i]: float(p) for i, p in enumerate(tag_probs)}
            
            # friendly/faith 델타 예측 (11 클래스: -5 ~ +5)
            friendly_class = torch.argmax(friendly_logits[0]).item()
            faith_class = torch.argmax(faith_logits[0]).item()
            
            friendly_delta = friendly_class - 5
            faith_delta = faith_class - 5
            
            friendly_prob = torch.softmax(friendly_logits[0], dim=0)[friendly_class].item()
            faith_prob = torch.softmax(faith_logits[0], dim=0)[faith_class].item()
            
            return {
                "pred_tags": pred_tags,
                "tag_probs": tag_probs_dict,
                "friendly_delta": friendly_delta,
                "faith_delta": faith_delta,
                "friendly_prob": friendly_prob,
                "faith_prob": faith_prob
            }
            
        except Exception as e:
            print(f"[ERROR] NpcAgent 예측 오류: {e}")
            return {"error": str(e)}

npc_agent = NpcAgent()
