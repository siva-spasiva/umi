# Umi Backend API

Umi는 게임 캐릭터와의 대화, 스탯 관리, 스토리 진행을 추적하는 FastAPI 기반 백엔드 서버입니다. MongoDB를 사용하여 대화 로그, 게임 스탯, 스토리 요약 등을 저장하고 관리합니다.

## 🚀 주요 기능

- **대화 로그 관리**: 게임 내 NPC와의 대화 내용을 일자별로 저장
- **스토리 요약**: LLM 기반 대화 요약 및 분석 결과 저장
- **스탯 시스템**: 캐릭터 및 NPC의 스탯(HP, 친밀도, 신뢰도 등) 관리
- **JWT 인증**: 보안이 적용된 API 엔드포인트
- **헬스 체크**: 서버 상태 모니터링

## 📁 프로젝트 구조

```
umi-backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 애플리케이션 진입점
│   ├── api/
│   │   └── v1/
│   │       ├── chat.py         # 대화 로그 및 스토리 요약 API
│   │       ├── health_check.py # 헬스 체크 API
│   │       └── stats.py        # 스탯 관리 API
│   ├── core/
│   │   ├── config.py          # 환경 설정
│   │   └── security.py        # JWT 인증 로직
│   ├── data/
│   │   └── characters.json    # 캐릭터 데이터
│   ├── schemas/
│   │   ├── chat.py           # 대화 로그 스키마
│   │   ├── stats.py          # 스탯 스키마
│   │   └── story.py          # 스토리 요약 스키마
│   └── services/
│       ├── chat_service.py    # 대화 및 스토리 비즈니스 로직
│       ├── health_service.py  # 헬스 체크 서비스
│       └── stats_service.py   # 스탯 관리 비즈니스 로직
├── Dockerfile
├── requirements.txt
└── README.md
```

## 🛠️ 기술 스택

- **Framework**: FastAPI
- **Database**: MongoDB (Motor - 비동기 드라이버)
- **Authentication**: JWT (JSON Web Token)
- **Server**: Uvicorn
- **Language**: Python 3.8+

## 📦 설치 방법

### 1. 저장소 클론

```bash
git clone <repository-url>
cd umi
```

### 2. 가상환경 생성 및 활성화

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 3. 의존성 설치

```bash
pip install -r requirements.txt
```

### 4. 환경 변수 설정

`.env` 파일을 프로젝트 루트에 생성하고 다음 내용을 입력:

```env
MONGODB_URL=mongodb://localhost:27017
DATABASE_NAME=umi_game
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
```

## 🚀 실행 방법

### 개발 서버 실행

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

서버가 실행되면 다음 주소로 접속 가능:

- API: `http://localhost:8000`
- API 문서 (Swagger): `http://localhost:8000/docs`
- API 문서 (ReDoc): `http://localhost:8000/redoc`

## 📡 API 엔드포인트

### 헬스 체크

- `GET /api/v1/health` - 서버 상태 확인

### 대화 로그 관리

- `POST /api/v1/save-log` - 대화 로그 저장
- `POST /api/v1/summary` - 대화 요약 저장
- `GET /api/v1/summary/{day_index}` - 특정 일자 요약 조회

### 스탯 관리

- `GET /api/v1/stats` - 현재 스탯 조회
- `POST /api/v1/stats` - 스탯 업데이트
- `POST /api/v1/stats/NPC` - NPC 스탯 업데이트
- `GET /api/v1/stats/static` - 초기 스탯 설정

## 📊 데이터 모델

### DayLog (대화 로그)

```python
{
  "day_index": 1,
  "conversation": {
    "participants": [...],
    "messages": [...]
  },
  "items_acquired": [...],
  "information_acquired": [...],
  "troll_level_events": [...]
}
```

### Stats (스탯)

```python
{
  "fishLevel": 10,
  "hp": 50,
  "friendly": 50,
  "faith": 50,
  "trust": 10,
  "npcStats": {...}
}
```

## 🔒 인증

API는 JWT 토큰 기반 인증을 사용합니다. 인증이 필요한 엔드포인트에 접근하려면:

1. 토큰을 획득
2. 요청 헤더에 포함: `Authorization: Bearer <token>`

## 🗄️ 데이터베이스 구조

### Collections

- **chat_logs**: 일자별 대화 로그
- **story_summaries**: LLM 생성 스토리 요약
- **stats**: 캐릭터 및 NPC 스탯

## 🐳 Docker 지원

```bash
docker build -t umi-backend .
docker run -p 8000:8000 --env-file .env umi-backend
```

## 📝 개발 가이드

### 새로운 API 엔드포인트 추가

1. `app/schemas/`에 새로운 스키마 정의
2. `app/services/`에 비즈니스 로직 구현
3. `app/api/v1/`에 라우터 생성
4. `app/main.py`에 라우터 등록

### 코드 스타일

- PEP 8 준수
- Type hints 사용 권장
- Pydantic 모델을 통한 데이터 검증

## 🤝 기여

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📧 문의

프로젝트 관련 문의사항이 있으시면 이슈를 등록해주세요.
