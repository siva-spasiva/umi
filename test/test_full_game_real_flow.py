"""
=============================================================
Full Game Real Flow Integration Test (AWS 실모델 연동 통합 테스트)
=============================================================

목적:
- Mock 없이 실제 API 서버를 호출합니다.
- API 서버가 연결한 GPU 서버(/health, /infer/ga1) 상태를 사전 검증합니다.
- 최소 게임 플로우(로그인 -> 스탯 초기화 -> 채팅 -> 세션 종료 -> 일기 생성 -> 요약 조회)를 실행합니다.

중요:
- 이 스크립트는 ASGITransport(인메모리) 사용하지 않습니다.
- 실제 네트워크 URL로 호출하므로 AWS/GPU 프록시 통신 경로를 검증합니다.

실행 예시:
    ./.venv/bin/python test/test_full_game_real_flow.py

환경 변수:
- REAL_FLOW_API_BASE_URL (default: http://127.0.0.1:8000)
- REAL_FLOW_GPU_URL      (default: http://127.0.0.1:8001)
- REAL_FLOW_DAY_INDEX    (default: 1)
- REAL_FLOW_SESSION_INDEX(default: 1)
- REAL_FLOW_CHAT_TURNS   (default: 2)
- REAL_FLOW_TIMEOUT_SEC  (default: 180)
"""

import asyncio
import json
import os
import time
from typing import Any, Dict, Optional

import httpx


API_BASE_URL = os.getenv("REAL_FLOW_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
GPU_URL = os.getenv("REAL_FLOW_GPU_URL", "http://127.0.0.1:8001").rstrip("/")
DAY_INDEX = int(os.getenv("REAL_FLOW_DAY_INDEX", "1"))
SESSION_INDEX = int(os.getenv("REAL_FLOW_SESSION_INDEX", "1"))
CHAT_TURNS = int(os.getenv("REAL_FLOW_CHAT_TURNS", "2"))
TIMEOUT_SEC = int(os.getenv("REAL_FLOW_TIMEOUT_SEC", "180"))
TOTAL_DAYS = int(os.getenv("REAL_FLOW_TOTAL_DAYS", "5"))

# 안정적인 NPC ID 후보(프로젝트 전반에서 사용되는 값)
NPC_ID = "galchi"
SAFE_MESSAGES = [
    "안녕하세요. 오늘 마을 분위기는 어떤가요?",
    "최근에 수상한 일이 있었는지 들은 게 있나요?",
    "혹시 제가 조심해야 할 장소가 있나요?",
]


def _timeout() -> httpx.Timeout:
    return httpx.Timeout(timeout=TIMEOUT_SEC, connect=10.0)


async def _request_json(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    expected_status: int,
    token: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    started = time.perf_counter()
    response = await client.request(method, path, json=payload, headers=headers)
    elapsed = time.perf_counter() - started

    print(f"[{method} {path}] status={response.status_code} elapsed={elapsed:.2f}s")

    if response.status_code != expected_status:
        raise RuntimeError(
            f"Request failed: {method} {path} (expected {expected_status}, got {response.status_code})\n"
            f"Response: {response.text}"
        )

    try:
        return response.json()
    except Exception as exc:
        raise RuntimeError(f"Invalid JSON response from {method} {path}: {response.text}") from exc


async def preflight_check_gpu() -> None:
    print("\n=== Preflight: GPU server health ===")
    async with httpx.AsyncClient(base_url=GPU_URL, timeout=_timeout()) as gpu_client:
        health = await _request_json(gpu_client, "GET", "/health", expected_status=200)
        print(json.dumps(health, ensure_ascii=False, indent=2))

        if health.get("status") != "ok":
            raise RuntimeError(f"GPU health status is not ok: {health}")

        if health.get("device") != "cuda":
            raise RuntimeError(f"GPU device is not cuda. Current: {health.get('device')}")

        models = health.get("models", {})
        required = ["ga1", "npc_analyzer", "npc_llm", "story"]
        missing = [name for name in required if not models.get(name)]
        if missing:
            raise RuntimeError(f"Required models are not loaded: {missing}")

        ga1 = await _request_json(
            gpu_client,
            "POST",
            "/infer/ga1",
            expected_status=200,
            payload={"message": "안녕하세요"},
        )
        print(f"GPU /infer/ga1 -> {ga1}")


async def run_real_flow() -> None:
    print("\n=== Real Flow Start ===")
    print(f"API_BASE_URL={API_BASE_URL}")
    print(f"GPU_URL={GPU_URL}")
    print(
        f"START_DAY={DAY_INDEX}, TOTAL_DAYS={TOTAL_DAYS}, "
        f"SESSION_INDEX={SESSION_INDEX}, CHAT_TURNS={CHAT_TURNS}"
    )

    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=_timeout()) as client:
        # 1) API health
        health = await _request_json(client, "GET", "/api/v1/health", expected_status=200)
        print(f"API health: {health}")

        # 2) Login
        login = await _request_json(client, "POST", "/api/v1/users/login", expected_status=200)
        token = login["access_token"]
        print("Login ok")

        # 3) Init stats
        stats = await _request_json(
            client,
            "GET",
            "/api/v1/stats/static",
            expected_status=200,
            token=token,
        )
        print(f"Stats initialized. keys={list(stats.keys())}")

        for day in range(DAY_INDEX, DAY_INDEX + TOTAL_DAYS):
            print(f"\n--- Day {day} ---")

            # 4) Real chat (AWS/GPU path expected in server config)
            for idx in range(CHAT_TURNS):
                msg = SAFE_MESSAGES[(day + idx) % len(SAFE_MESSAGES)]
                chat = await _request_json(
                    client,
                    "POST",
                    "/api/v1/chat",
                    expected_status=200,
                    token=token,
                    payload={"npcId": NPC_ID, "message": msg},
                )
                preview = str(chat.get("response", ""))[:80].replace("\n", " ")
                print(f"Day {day} chat turn {idx + 1}: {preview}")

            # 5) End session (summary + memory path)
            end_session = await _request_json(
                client,
                "POST",
                "/api/v1/end-session",
                expected_status=200,
                token=token,
                payload={
                    "day_index": day,
                    "session_index": SESSION_INDEX,
                },
            )
            print(f"Day {day} end-session status: {end_session.get('status')}")

            # 6) Generate diary (real story generation path)
            diary = await _request_json(
                client,
                "POST",
                "/api/v1/diary",
                expected_status=201,
                token=token,
                payload={"day_index": day},
            )
            print(f"Day {day} diary generated for day={diary.get('day_index')}")

            # 7) Read summary
            summary = await _request_json(
                client,
                "GET",
                f"/api/v1/summary/{day}",
                expected_status=200,
                token=token,
            )
            diary_title = summary.get("diary", {}).get("title", "")
            print(f"Day {day} summary retrieved. diary.title={diary_title}")

        # 8) Generate ending on completion (day 5 target)
        ending = await _request_json(
            client,
            "POST",
            "/api/v1/ending",
            expected_status=200,
            token=token,
        )
        print(
            "Ending generated: "
            f"title={ending.get('title', '')}, "
            f"type={ending.get('ending_type', '')}"
        )

        # 9) Read epilogue and cross-check
        epilogue = await _request_json(
            client,
            "GET",
            "/api/v1/epilogue",
            expected_status=200,
            token=token,
        )
        if epilogue.get("title") != ending.get("title"):
            raise RuntimeError("Epilogue title mismatch with generated ending")
        print("Epilogue verified.")

    print("\n=== Real Flow Completed Successfully ===")


async def main() -> None:
    await preflight_check_gpu()
    await run_real_flow()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted by user")
