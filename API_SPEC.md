# Umi Backend API Spec (Frontend 연동용)

기준: `app/api/v1` 실제 코드 기준 정리 (2026-02-26)

## 0) 로컬 실행

### 사전 요구사항

- Docker Desktop 실행 중

### 실행

```bash
bash scripts/bootstrap.sh
```

내부적으로 다음 순서로 진행된다:

1. `docker compose -f docker-compose.local.yml up -d --build`
   - `umi-mongo-local` (MongoDB 7): `localhost:27017`
   - `umi-api-local` (FastAPI + uvicorn): `localhost:8000`
2. `GET /api/v1/health` 폴링 (2초 간격, 최대 60회) → healthy 확인
3. ~~`python -m app.data.init_data` 시드 데이터 초기화~~ (모듈 미구현, 스킵)

### 접속

| 대상 | URL |
| --- | --- |
| API | <http://localhost:8000> |
| Swagger 문서 | <http://localhost:8000/docs> |

### 로컬 환경 특이사항

- `MOCK_MODE=true` — GPU/임베딩 모델 호출 없이 Mock 응답
- `UMI_DISABLE_VECTORDB=true` — ChromaDB 비활성화
- `USE_GPU_PROXY=false` — GPU 서버 연결 안 함
- 테스트용 토큰: `magic_token_for_test` (Authorization 헤더에 사용 가능)

### 종료

```bash
docker compose -f docker-compose.local.yml down
```

---

## 1) 기본 정보

- Base URL: `/api/v1`
- 인증: `Authorization: Bearer <access_token>`
- 콘텐츠 타입: `application/json`
- 공통 에러 포맷(FastAPI 기본): `{ "detail": "에러 메시지" }`

## 2) 인증/세션

### `POST /api/v1/users/login`
- Auth: 불필요
- 설명: 익명 로그인, Access/Refresh 토큰 발급
- Response:
```json
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "bearer"
}
```

### `POST /api/v1/users/refresh`
- Auth: 불필요
- Request:
```json
{
  "refresh_token": "string"
}
```
- Response:
```json
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "bearer"
}
```
- Error: `401` (유효하지 않거나 만료된 리프레시 토큰)

## 3) 상태/모니터링

### `GET /api/v1/health`
- Auth: 불필요
- Response:
```json
{
  "status": "ok",
  "components": {
    "server": "running",
    "database": "healthy"
  }
}
```

### `GET /api/v1/monitor`
- Auth: 불필요
- 설명: CPU/RAM/Disk/GPU 상태 조회

### `GET /api/v1/monitor/dashboard`
- Auth: 불필요
- 설명: HTML 대시보드 반환

## 4) Stats

### `GET /api/v1/stats`
- Auth: 필요
- Response (`StatsResponse`):
```json
{
  "fishLevel": 0,
  "total_hp": 100,
  "session_hp": 30,
  "plus_hp": 0,
  "current_session": "morning",
  "current_session_index": 1,
  "current_day": 0,
  "floor_id": "B1",
  "room_id": "cafeteria"
}
```

### `POST /api/v1/stats`
- Auth: 필요
- Request:
```json
{
  "updates": {
    "floor_id": "B2",
    "room_id": "room001"
  }
}
```
- Response: `FirstStatsResponse` 형식 (위와 동일 계열)

### `POST /api/v1/stats/NPC`
- Auth: 필요
- Request:
```json
{
  "npcId": "NPC_KWAK_01",
  "updates": {
    "friendly": 60,
    "faith": 55
  }
}
```
- Response (`NPCStat`):
```json
{
  "friendly": 60,
  "faith": 55,
  "fishLevel": 0
}
```

### `GET /api/v1/stats/static`
- Auth: 필요
- 설명: 초기 유저 스탯/초기 인벤토리 생성
- Response:
```json
{
  "fishLevel": 0,
  "total_hp": 100,
  "session_hp": 30,
  "plus_hp": 0,
  "current_session": "morning",
  "current_session_index": 1,
  "current_day": 0
}
```

### `POST /api/v1/stats/hp/spend`
- Auth: 필요
- Request:
```json
{
  "hp": 10,
  "message": "NPC 대화",
  "floor_id": "B1",
  "room_id": "cafeteria"
}
```
- Response (`SpendHpResponse`):
```json
{
  "success": true,
  "total_hp": 90,
  "session_hp": 20,
  "plus_hp": 0,
  "current_session": "morning",
  "current_session_index": 1,
  "current_day": 0,
  "session_depleted": false,
  "message": "NPC 대화",
  "floor_id": "B1",
  "room_id": "cafeteria"
}
```

## 5) Chat / Story

### `POST /api/v1/chat`
- Auth: 필요
- 설명: NPC 대화 (호출 시 HP 10 소모)
- Request:
```json
{
  "message": "안녕?",
  "npcId": "NPC_KWAK_01",
  "item_id": "item001"
}
```
- Success Response 예:
```json
{
  "response": "NPC 응답",
  "npcId": "NPC_KWAK_01",
  "status": "success",
  "analysis": {},
  "state": {},
  "hp": {
    "success": true,
    "total_hp": 90,
    "session_hp": 20,
    "plus_hp": 0,
    "current_session": "morning",
    "current_session_index": 1,
    "current_day": 0,
    "session_depleted": false
  }
}
```
- Guardrail Block 응답 예:
```json
{
  "response": "차단 메시지",
  "blocked": true
}
```
- Error: `400` (HP 부족)

### `POST /api/v1/save-log`
- Auth: 불필요
- Request: `DayLog`
- Response:
```json
{
  "status": "success",
  "log_id": "mongo_object_id"
}
```

### `POST /api/v1/summary`
- Auth: 불필요
- Request: `StorySummary`
- Response:
```json
{
  "status": "success",
  "action": "inserted",
  "day_index": 1
}
```

### `POST /api/v1/diary`
- Auth: 필요
- Request:
```json
{
  "day_index": 1
}
```
- Response:
```json
{
  "status": "success",
  "day_index": 1,
  "data": { }
}
```
`data`는 `StorySummary`.

### `GET /api/v1/summary/{day_index}`
- Auth: 필요
- Response: `StorySummary`
- Error: `404`

### `POST /api/v1/end-session`
- Auth: 필요
- Request:
```json
{
  "day_index": 1,
  "session_index": 2
}
```
- 주요 응답 패턴:
  - `status: "tutorial"`
  - `status: "skipped"`
  - `status: "success"`
- 공통적으로 `advance`(세션 전환 결과) 포함

### `POST /api/v1/ending`
- Auth: 필요
- 설명: 최종 엔딩 생성/저장
- Response (`EpilogueResponse`)

### `GET /api/v1/epilogue`
- Auth: 필요
- 설명: 저장된 엔딩 조회
- Response (`EpilogueResponse`)
- Error: `404`

### `POST /api/v1/eavesdrop`
- Auth: 필요
- 설명: 추가 엿듣기, HP 5 소모
- Request:
```json
{
  "day_index": 1,
  "session_index": 2,
  "room_id": "cafeteria"
}
```
- Response:
```json
{
  "conversation": {
    "topic": "string",
    "turns": [],
    "npc_states": {}
  },
  "can_eavesdrop_more": true
}
```

## 6) Conversation

### `POST /api/v1/conversation/start`
- Auth: 필요
- 설명: NPC 자동 대화 시작 (호출 시 HP 10 소모)
- 수동 모드 Request:
```json
{
  "topic": "최근 사건",
  "npc_ids": ["NPC_KWAK_01", "NPC_CHEONG_02"],
  "num_turns": 5
}
```
- 스케줄 모드 Request:
```json
{
  "day_index": 2,
  "session": "morning"
}
```
- Response: `ConversationResponse[]`
- Error: `400` (HP 부족/필수값 누락)

### `POST /api/v1/conversation/reply`
- Auth: 필요
- Request:
```json
{
  "topic": "최근 사건",
  "npc_ids": ["NPC_KWAK_01", "NPC_CHEONG_02"],
  "user_message": "너희는 어떻게 생각해?",
  "history": [
    { "speaker": "곽빙어", "speaker_id": "NPC_KWAK_01", "content": "..." }
  ]
}
```
- Response (`ConversationResponse`):
```json
{
  "topic": "최근 사건",
  "turns": [
    { "speaker": "user", "speaker_id": "user", "content": "..." },
    { "speaker": "곽빙어", "speaker_id": "NPC_KWAK_01", "content": "...", "analysis": {} }
  ],
  "npc_states": {
    "NPC_KWAK_01": { "friendly": 60, "faith": 55 }
  }
}
```

## 7) Map

Map 라우터 prefix: `/api/v1/map`

### `GET /api/v1/map/`
- Auth: 필요
- Response: `Floor[]`

### `GET /api/v1/map/{floor_id}`
- Auth: 필요
- Response: `Floor`
- Error: `404`

### `GET /api/v1/map/{floor_id}/room/{room_id}`
- Auth: 필요
- Response 예:
```json
{
  "room": { },
  "npcs": ["NPC_KWAK_01", "NPC_CHEONG_02"],
  "topic": { "title": "string", "context": "string" },
  "single_npc": null
}
```

### `POST /api/v1/map/{floor_id}/room/{room_id}/eavesdrop`
- Auth: 필요
- 설명: 해당 방의 최초 엿듣기, HP 5 소모
- Response:
```json
{
  "npcs": ["NPC_KWAK_01", "NPC_CHEONG_02"],
  "topic": { "title": "string", "context": "string" },
  "conversation": {
    "topic": "string",
    "turns": [],
    "npc_states": {}
  },
  "can_eavesdrop_more": true
}
```

## 8) Inventory

Inventory 라우터 prefix: `/api/v1/inventory`

### `GET /api/v1/inventory`
- Auth: 필요
- Response (`InventoryResponse`):
```json
{
  "user_id": "string",
  "items": [
    {
      "id": "item001",
      "name": "string",
      "description": "string",
      "flavorText": "string",
      "type": "normal",
      "owned": true,
      "consumable": true,
      "effect": {},
      "npcOrigin": null,
      "isContract": false,
      "roomItem": true,
      "icon": "🔑"
    }
  ],
  "record_files": []
}
```

### `POST /api/v1/inventory/add`
- Auth: 필요
- Request:
```json
{ "item_id": "item001" }
```
- Response: `InventoryResponse`

### `POST /api/v1/inventory/use`
- Auth: 필요
- Request:
```json
{ "item_id": "item001" }
```
- Response:
```json
{
  "status": "success",
  "message": "item001 아이템을 사용했습니다."
}
```
- Error: `404` (보유하지 않은 아이템)

### `POST /api/v1/inventory/explore`
- Auth: 필요
- 설명: 탐색 시 HP 1 소모 후 아이템 획득 처리
- Request:
```json
{
  "floor_id": "B1",
  "room_id": "cafeteria",
  "active_zone_id": "zone_001"
}
```
- Response (`ExploreResponse`):
```json
{
  "success": true,
  "floor_id": "B1",
  "room_id": "cafeteria",
  "active_zone_id": "zone_001",
  "item_found": true,
  "item": {},
  "message": "아이템 획득 메시지"
}
```
- Error: `400` (HP 부족), `404` (탐색 실패)

## 9) Records

Records 라우터 prefix: `/api/v1/records`

### `POST /api/v1/records`
- Auth: 필요
- Request:
```json
{
  "title": "첫 녹음",
  "messages": [
    { "speaker": "user", "content": "..." }
  ]
}
```
- Response:
```json
{
  "status": "success",
  "record_id": "uuid"
}
```

### `GET /api/v1/records/list`
- Auth: 필요
- Response: `RecordingListResponse[]`

### `GET /api/v1/records/{record_id}`
- Auth: 필요
- Response: `Recording`
- Error: `404`

## 10) Debug (개발용)

### `POST /api/v1/debug/set_npc_state`
- Auth: 불필요
- Request:
```json
{
  "npc_id": "NPC_KWAK_01",
  "friendly": 60,
  "faith": 60
}
```

### `POST /api/v1/debug/reset_troll_count`
- Auth: 필요

### `POST /api/v1/debug/set_session_hp`
- Auth: 필요
- Request:
```json
{
  "session_hp": 30,
  "plus_hp": 5,
  "total_hp": 100
}
```

## 11) 프론트 연동 추천 순서

1. `POST /users/login`으로 토큰 획득
2. 헤더에 `Authorization: Bearer <access_token>` 세팅
3. 최초 1회 `GET /stats/static` 호출 (초기 데이터 생성)
4. 화면 진입 시 기본 병렬 호출:
   - `GET /stats`
   - `GET /inventory`
   - `GET /map/` 또는 `GET /map/{floor_id}`
5. 상호작용 시:
   - 일반 대화: `POST /chat`
   - 자동 대화: `POST /conversation/start`
   - 아이템 탐색: `POST /inventory/explore`
6. 세션 종료 시 `POST /end-session`, 일기/엔딩은 `POST /diary`, `POST /ending`

## 12) 구현 시 주의사항

- 토큰 만료/검증 실패 시 `401`
- 스탯/대화/탐색 API 다수가 HP 부족 시 `400`
- 일부 엔드포인트는 `response_model` 없이 동적 응답(예: `/chat`, `/end-session`)
- 로컬 테스트용 특수 토큰: `magic_token_for_test` (코드에 하드코딩)
