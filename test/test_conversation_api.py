#!/usr/bin/env python3
"""
NPC 대화(Conversation) API 테스트 스크립트

테스트 시나리오:
1. NPC-only 모드: NPC 2명이 주제를 가지고 자동 대화
2. User+NPC 모드: 유저 + NPC 2명이 주제를 가지고 대화

사용법:
    python test_conversation_api.py
    python test_conversation_api.py --gpu-direct   # GPU 서버 직접 호출
"""

import sys
import os

# 스크립트 실행 위치와 상관없이 Umi 프로젝트 루트를 PYTHONPATH에 추가하여 'app' 모듈을 찾을 수 있게 함
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
import time
import httpx
import argparse
from typing import Optional
from app.core.security import create_access_token


# ============================================================
# 설정
# ============================================================

LOCAL_SERVER_URL = "http://localhost:8000"
GPU_SERVER_URL = "http://localhost:8001"

# 테스트에 사용할 유효한 인증 토큰 생성
test_token = create_access_token("test_user_001")

AUTH_HEADERS = {
    "Authorization": f"Bearer {test_token}",
    "Content-Type": "application/json"
}


def print_separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def print_turn(turn: dict, index: int):
    speaker = turn.get("speaker", "?")
    content = turn.get("content", "")
    analysis = turn.get("analysis")

    print(f"  [{index}] {speaker}: {content}")
    if analysis:
        tags = analysis.get("reason_tags", [])
        fd = analysis.get("friendly_delta", 0)
        fad = analysis.get("faith_delta", 0)
        print(f"      [분석] 태그={tags}, 호감={fd:+d}, 신뢰={fad:+d}")


# ============================================================
# 테스트 1: NPC-only 자동 대화
# ============================================================

def test_npc_only_conversation(base_url: str, headers: dict):
    """NPC-only 모드: NPC 2명이 주제를 가지고 자동 대화"""
    print_separator("테스트 1: NPC-only 자동 대화 (곽빙어 + 청갈치)")

    payload = {
        "topic": "교단 내부에 숨겨진 비밀 금고에 대해",
        "npc_ids": ["bingeo", "galchi"],
        "num_turns": 4
    }

    print(f"📝 주제: {payload['topic']}")
    print(f"🎭 참여 NPC: {payload['npc_ids']}")
    print(f"🔄 턴 수: {payload['num_turns']}")
    print()

    try:
        start = time.time()
        if "/api/v1" in base_url or base_url == LOCAL_SERVER_URL:
            resp = httpx.post(
                f"{base_url}/api/v1/conversation/start",
                json=payload,
                headers=headers,
                timeout=300
            )
        else:
            # GPU 서버 직접 호출
            resp = httpx.post(
                f"{base_url}/infer/npc/conversation",
                json={**payload, "include_user": False},
                timeout=300
            )
        elapsed = time.time() - start

        resp.raise_for_status()
        data = resp.json()
        
        if isinstance(data, list):
            data = data[0] if len(data) > 0 else {}

        print(f"✅ 응답 성공 ({elapsed:.2f}s)\n")

        turns = data.get("turns", [])
        for i, turn in enumerate(turns, 1):
            print_turn(turn, i)

        print(f"\n📊 NPC 상태:")
        for npc_id, state in data.get("npc_states", {}).items():
            print(f"  {npc_id}: {state}")

        return True

    except httpx.ConnectError:
        print(f"❌ 서버에 연결할 수 없습니다: {base_url}")
        return False
    except Exception as e:
        print(f"❌ 오류: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Response: {e.response.text}")
        return False


# ============================================================
# 테스트 2: User+NPC 대화
# ============================================================

def test_user_npc_conversation(base_url: str, headers: dict):
    """User+NPC 모드: 유저 + NPC 2명 대화"""
    print_separator("테스트 2: User+NPC 대화 (유저 + 청갈치 + 박복어)")

    payload = {
        "topic": "교단의 미래에 대해",
        "npc_ids": ["galchi", "bokeo"],
        "user_message": "너희들은 교단의 미래가 어떻게 될 거라고 생각해?",
        "history": []
    }

    print(f"📝 주제: {payload['topic']}")
    print(f"🎭 참여 NPC: {payload['npc_ids']}")
    print(f"💬 유저 메시지: {payload['user_message']}")
    print()

    try:
        start = time.time()
        if "/api/v1" in base_url or base_url == LOCAL_SERVER_URL:
            resp = httpx.post(
                f"{base_url}/api/v1/conversation/reply",
                json=payload,
                headers=headers,
                timeout=300
            )
        else:
            # GPU 서버 직접 호출
            resp = httpx.post(
                f"{base_url}/infer/npc/conversation",
                json={**payload, "include_user": True},
                timeout=300
            )
        elapsed = time.time() - start

        resp.raise_for_status()
        data = resp.json()

        print(f"✅ 응답 성공 ({elapsed:.2f}s)\n")

        turns = data.get("turns", [])
        for i, turn in enumerate(turns, 1):
            print_turn(turn, i)

        print(f"\n📊 NPC 상태:")
        for npc_id, state in data.get("npc_states", {}).items():
            print(f"  {npc_id}: {state}")

        # ── 후속 메시지 테스트 (멀티턴) ──
        print_separator("테스트 2-b: 후속 유저 메시지 (멀티턴)")

        # 이전 턴들을 히스토리로 변환
        history_for_next = [
            {
                "speaker": t.get("speaker", ""),
                "speaker_id": t.get("speaker_id", ""),
                "content": t.get("content", "")
            }
            for t in turns
        ]

        follow_up_payload = {
            "topic": "교단의 미래에 대해",
            "npc_ids": ["galchi", "bokeo"],
            "user_message": "그럼 전광어는 진짜 뭘 숨기고 있는 걸까?",
            "history": history_for_next
        }

        print(f"💬 유저 후속 메시지: {follow_up_payload['user_message']}")
        print(f"📜 히스토리 턴 수: {len(history_for_next)}")
        print()

        start2 = time.time()
        if "/api/v1" in base_url or base_url == LOCAL_SERVER_URL:
            resp2 = httpx.post(
                f"{base_url}/api/v1/conversation/reply",
                json=follow_up_payload,
                headers=headers,
                timeout=300
            )
        else:
            resp2 = httpx.post(
                f"{base_url}/infer/npc/conversation",
                json={**follow_up_payload, "include_user": True},
                timeout=300
            )
        elapsed2 = time.time() - start2

        resp2.raise_for_status()
        data2 = resp2.json()

        print(f"✅ 후속 응답 성공 ({elapsed2:.2f}s)\n")

        turns2 = data2.get("turns", [])
        for i, turn in enumerate(turns2, 1):
            print_turn(turn, i)

        return True

    except httpx.ConnectError:
        print(f"❌ 서버에 연결할 수 없습니다: {base_url}")
        return False
    except Exception as e:
        print(f"❌ 오류: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Response: {e.response.text}")
        return False


# ============================================================
# 테스트 3: 단일 NPC 대화
# ============================================================

def test_single_npc_conversation(base_url: str, headers: dict):
    """단일 NPC 자동 대화"""
    print_separator("테스트 3: 단일 NPC 자동 대화 (전광어 혼잣말)")

    payload = {
        "topic": "신도들의 충성심에 대한 평가",
        "npc_ids": ["gwangeo"],
        "num_turns": 3
    }

    print(f"📝 주제: {payload['topic']}")
    print(f"🎭 참여 NPC: {payload['npc_ids']}")
    print()

    try:
        start = time.time()
        if "/api/v1" in base_url or base_url == LOCAL_SERVER_URL:
            resp = httpx.post(
                f"{base_url}/api/v1/conversation/start",
                json=payload,
                headers=headers,
                timeout=300
            )
        else:
            resp = httpx.post(
                f"{base_url}/infer/npc/conversation",
                json={**payload, "include_user": False},
                timeout=300
            )
        elapsed = time.time() - start

        resp.raise_for_status()
        data = resp.json()
        
        if isinstance(data, list):
            data = data[0] if len(data) > 0 else {}

        print(f"✅ 응답 성공 ({elapsed:.2f}s)\n")

        for i, turn in enumerate(data.get("turns", []), 1):
            print_turn(turn, i)

        return True

    except Exception as e:
        print(f"❌ 오류: {e}")
        return False


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NPC 대화 API 테스트")
    parser.add_argument("--gpu-direct", action="store_true",
                        help="GPU 서버 직접 호출 (기본: 로컬 서버 경유)")
    parser.add_argument("--url", type=str, default=None,
                        help="서버 URL 직접 지정")
    parser.add_argument("--test", type=int, default=None,
                        help="특정 테스트만 실행 (1, 2, 3)")
    args = parser.parse_args()

    if args.url:
        base_url = args.url.rstrip("/")
    elif args.gpu_direct:
        base_url = GPU_SERVER_URL
    else:
        base_url = LOCAL_SERVER_URL

    print(f"🎯 테스트 대상: {base_url}")

    # 서버 상태 확인
    try:
        if args.gpu_direct:
            health = httpx.get(f"{base_url}/health", timeout=5)
        else:
            health = httpx.get(f"{base_url}/api/v1/health", timeout=5)
        print(f"✅ 서버 연결 확인")
    except Exception as e:
        print(f"⚠️ 서버 연결 실패: {e}")
        print("서버가 실행 중인지 확인해주세요.")

    results = {}

    if args.test is None or args.test == 1:
        results["NPC-only"] = test_npc_only_conversation(base_url, AUTH_HEADERS)
    if args.test is None or args.test == 2:
        results["User+NPC"] = test_user_npc_conversation(base_url, AUTH_HEADERS)
    if args.test is None or args.test == 3:
        results["Single NPC"] = test_single_npc_conversation(base_url, AUTH_HEADERS)

    # 결과 요약
    print_separator("테스트 결과 요약")
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status} - {name}")
