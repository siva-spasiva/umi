# Umi 서버 API 명세서 (상세 코드 포함)

이 문서는 Umi 서버의 API 엔드포인트와 해당 Request/Response 모델을 상세히 설명합니다.

## 기본 정보
- **Base URL**: `/api/v1`
- **Authentication**: `Authorization: Bearer <access_token>` (대부분의 엔드포인트)

---

## 1. 시스템 상태 (Health Check)

### GET /api/v1/health
서버와 데이터베이스의 연결 상태를 확인합니다.

#### Response
```json
{
  "status": "ok", // 전체 시스템 상태 ("ok" 또는 "error")
  "components": {
    "server": "running", // API 서버 상태
    "database": "healthy" // DB 연결 상태 ("healthy" 또는 에러 메시지)
  }
}
```

---

## 2. 인증 및 유저 스탯 (Auth & Stats)

### POST /api/v1/stats/static
초기 세션을 생성하고 로그인 처리합니다. (토큰 발급)

#### Response (`FirstStatsResponse`)
```python
class FirstStatsResponse(BaseModel):
    fishLevel: int      # 초기 물고기 레벨
    hp: int             # 초기 체력
    friendly: int       # 초기 유저 친밀도 (기본값 50)
    trust: int          # 초기 신뢰도
    token: str          # 발급된 Access Token (Authorization 헤더에 사용)
    refresh_token: str  # 발급된 Refresh Token (토큰 갱신용)
```

### POST /api/v1/refresh
만료된 액세스 토큰을 갱신합니다.

#### Request (`RefreshTokenRequest`)
```python
class RefreshTokenRequest(BaseModel):
    refresh_token: str  # 이전에 발급받은 Refresh Token
```

#### Response (`TokenResponse`)
```python
class TokenResponse(BaseModel):
    access_token: str           # 새로 발급된 Access Token
    refresh_token: str = None   # (선택) 새로 발급된 Refresh Token (Rotation시 제공)
    token_type: str = "bearer"  # 토큰 타입 (항상 "bearer")
```

### GET /api/v1/stats
현재 유저의 스탯을 조회합니다.

#### Response (`StatsResponse`)
```python
class StatsResponse(BaseModel):
    fishLevel: int  # 현재 물고기 레벨
    hp: int         # 현재 체력
    friendly: int   # 현재 유저 친밀도 (0-100)
    faith: int      # 현재 신앙심 (0-100)
    trust: int      # 현재 신뢰도 (0-100)
```

### POST /api/v1/stats
유저 스탯을 부분적으로 업데이트합니다.

#### Request (`StatsUpdate`)
```python
class StatsUpdate(BaseModel):
    # 업데이트할 스탯 필드와 값 (예: {"hp": 80, "trust": 10})
    updates: Dict[str, Any] 
```

### POST /api/v1/stats/NPC
특정 NPC의 스탯(친밀도, 신앙심 등)을 업데이트합니다.

#### Request (`NPCStatsUpdate`)
```python
class NPCStatsUpdate(BaseModel):
    npcId: str              # 대상 NPC ID (예: "believer_a")
    # 업데이트할 NPC 스탯 (예: {"friendly": 60, "faith": 70})
    updates: Dict[str, int] 
```

#### Response (`NPCStat`)
```python
class NPCStat(BaseModel):
    friendly: int   # NPC와의 친밀도 (0-100)
    faith: int      # NPC의 신앙심 또는 충성도 (0-100)
    fishLevel: int  # NPC와 관련된 물고기 레벨
```

---

## 3. 채팅 (Chat)

### POST /api/v1/chat
NPC와 대화합니다. 가드레일이 적용되어 입력/출력을 검증합니다.

#### Request (`ChatRequest`)
```python
class ChatRequest(BaseModel):
    message: str                # 유저가 보낸 메시지 내용
    npcId: str                  # 대화할 NPC ID
    userId: str = "user_dev"    # (옵션) 유저 ID, 기본값은 개발용 세션
```

#### Response (`ChatResponse`)
```python
class ChatResponse(BaseModel):
    response: str               # NPC의 응답 텍스트
    thought: str                # NPC의 내적 사고 (화면에 표시 안 할 수 있음)
    npcId: str                  # 응답한 NPC ID
    currentStats: Dict[str, Any] # 현재 유저 스탯 상태
    updatedStats: Dict[str, Any] # 이번 대화로 변경된 스탯 (없으면 빈 객체)
```

### POST /api/v1/save-log
'기록' 탭이나 일기 등을 위해 하루치 대화 로그를 저장합니다.

#### Request (`DayLog`)
```python
class DayLog(BaseModel):
    day_index: int              # 게임 내 일차 (1~7)
    conversation: Conversation  # 대화 전체 내역 (참여자, 메시지 리스트)
    items_acquired: List        # 획득한 아이템 목록
    information_acquired: List  # 획득한 정보 목록
    troll_level_events: List    # 트롤링 이벤트 목록
    state_snapshot: StateSnapshot # 당시 유저/게임 상태 스냅샷
```

### POST /api/v1/end-day
하루를 종료하고 세션을 요약하여 장기 기억(Vector DB)에 저장합니다.

#### Request (`EndDayRequest`)
```python
class EndDayRequest(BaseModel):
    day_index: int       # 종료할 일차
    npc_id: str = None   # (선택) 특정 NPC만 요약 처리할 경우 지정
```

---

## 4. 스토리 요약 (Story Analysis)

### POST /api/v1/summary
LLM이 분석한 하루치 스토리 요약을 저장합니다.

#### Request (`StorySummary`)
```python
class StorySummary(BaseModel):
    day_index: int                  # 일차
    diary: Diary                    # 생성된 일기 (제목, 내용, 어조)
    summary_bullets: List[str]      # 요약 항목 (bullet points)
    key_conversations: List[KeyConversation] # 주요 대화 내용 및 변화
    items: List[ItemUsage]          # 아이템 사용 및 함의
    clues: List[Clue]               # 획득한 단서 및 중요도
    troll_level_analysis: TrollAnalysis # 트롤링 분석
    consistency_check: ConsistencyCheck # 설정 모순/누락 확인
    ending: GameEnding              # 엔딩 조건 달성 여부
    flags_for_next_day: List[NextDayFlag] # 다음 날을 위한 플래그
    safety: SafetyCheck             # 안전성 검사 (환각/스포일러)
```

### GET /api/v1/summary/{day_index}
저장된 특정 일차의 스토리 요약을 조회합니다.

#### Response
`StorySummary` 모델과 동일한 구조를 반환합니다.

---

## 5. 대화 시나리오 자동화 (Conversation Auto-Play)

### POST /api/v1/conversation/start
[NPC-only] 유저 없이 NPC들끼리 자동으로 대화합니다.

#### Request (`ConversationStartRequest`)
```python
class ConversationStartRequest(BaseModel):
    topic: str              # 대화 주제
    npc_ids: List[str]      # 참여 NPC ID 목록 (1~3명)
    num_turns: int = 5      # 생성할 대화 턴 수
```

#### Response (`ConversationResponse`)
```python
class ConversationResponse(BaseModel):
    topic: str
    turns: List[ConversationTurn] # 생성된 대화 턴 목록
    npc_states: Dict[str, Dict]   # 대화 후 변경된 NPC 상태들
```

#### Sub-Model (`ConversationTurn`)
```python
class ConversationTurn(BaseModel):
    speaker: str    # 화자 이름 (NPC 한국어 이름)
    speaker_id: str # 화자 ID
    content: str    # 대사 내용
    analysis: Dict  # (옵션) 의도/감정 분석 결과
```

### POST /api/v1/conversation/reply
[User+NPC] 진행 중인 대화에 유저가 개입합니다.

#### Request (`ConversationReplyRequest`)
```python
class ConversationReplyRequest(BaseModel):
    topic: str              # 대화 주제
    npc_ids: List[str]      # 참여 NPC ID 목록
    user_message: str       # 유저의 발언 내용
    # 이전 대화 기록 (맥락 유지를 위해 필요)
    history: List[Dict[str, Any]] 
```

---

## 6. 인벤토리 (Inventory)

### GET /api/v1/inventory
유저의 인벤토리와 녹음 파일 목록을 조회합니다.

#### Response (`InventoryResponse`)
```python
class InventoryResponse(BaseModel):
    user_id: str
    # 아이템 코드별 보유 여부 (예: {"001": true, "002": false})
    items: Dict[str, bool] 
    # 녹음 파일 메타데이터 목록 (id, title, created_at 등)
    record_files: List[Dict] 
```

### POST /api/v1/inventory/add
아이템을 획득(추가)합니다.

#### Request (`ItemActionRequest`)
```python
class ItemActionRequest(BaseModel):
    item_id: str  # 아이템 코드 (예: "001")
```

### POST /api/v1/inventory/use
아이템을 사용(소모)합니다.

#### Request (`ItemActionRequest`)
```python
class ItemActionRequest(BaseModel):
    item_id: str  # 사용할 아이템 코드
```

---

## 7. 녹음 (Records)

### POST /api/v1/records
대화 내용을 녹음 파일로 저장합니다.

#### Request (`SaveRecordingRequest`)
```python
class SaveRecordingRequest(BaseModel):
    # 대화 메시지 리스트 (화자, 내용, 시간 등)
    messages: List[Dict[str, Any]] 
    title: str = None  # (선택) 녹음 파일 제목
```

---

## 8. 모니터링 (Monitoring)

### GET /api/v1/monitor
시스템 리소스 사용량을 조회합니다.

#### Response
```json
{
  "cpu": { "usage_percent": 12.5 },
  "memory": { "percent": 45.2, "available_gb": 8.5 },
  "gpu": [
    {
      "index": 0,
      "name": "NVIDIA GeForce RTX 3090",
      "gpu_utilization": 30,
      "memory_used_gb": 4.2,
      ...
    }
  ]
}
```
