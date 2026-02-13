"""
Prompt A/B Test: 영어 vs 한국어 시스템 프롬프트 성능 비교
- GPU 서버(/infer/npc)를 직접 호출하여 응답 시간과 품질을 측정합니다.
- Phase 1: 현재 영어 프롬프트로 50회 호출
- Phase 2: 한국어 프롬프트로 변경 후 50회 호출
- 결과를 JSON으로 저장하고 통계 요약을 출력합니다.

사용법:
    python test_prompt_ab.py --phase english --count 50
    python test_prompt_ab.py --phase korean --count 50
    python test_prompt_ab.py --compare
"""

import argparse
import httpx
import json
import time
import statistics
import os
from datetime import datetime


# ============================================================
# 설정
# ============================================================

GPU_SERVER_URL = os.getenv("GPU_SERVER_URL", "http://localhost:8001")
DEFAULT_NPC_ID = "CHEONGGALCHI"
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ab_test_results")

# 테스트에 사용할 다양한 유저 메시지 (10개 → 50회에 5번씩 반복)
TEST_MESSAGES = [
    "안녕? 넌 누구야?",
    "이 마을에 대해 알려줘.",
    "요즘 바다에서 이상한 일이 일어나고 있다던데?",
    "나는 너를 믿어도 될까?",
    "혹시 비밀 같은 거 알고 있어?",
    "물고기가 이상하게 변했다는 소문이 있던데...",
    "네가 가장 좋아하는 게 뭐야?",
    "여기서 일하는 건 어때?",
    "다른 사람들은 뭐라고 해?",
    "오늘 날씨가 참 좋다, 그렇지?",
]


# ============================================================
# API 호출
# ============================================================

def call_npc_api(
    message: str,
    npc_id: str = DEFAULT_NPC_ID,
    history: list = None
) -> dict:
    """
    GPU 서버의 /infer/npc 엔드포인트를 동기적으로 호출합니다.

    Returns:
        {
            "response": str,
            "response_time": float (초),
            "status_code": int,
            "error": str or None
        }
    """
    payload = {
        "npc_id": npc_id,
        "message": message,
        "history": history,
    }

    start = time.perf_counter()
    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(f"{GPU_SERVER_URL}/infer/npc", json=payload)
            elapsed = time.perf_counter() - start

            if resp.status_code == 200:
                data = resp.json()
                return {
                    "response": data.get("response", ""),
                    "state": data.get("state"),
                    "analysis": data.get("analysis"),
                    "response_time": round(elapsed, 4),
                    "status_code": 200,
                    "error": None,
                }
            else:
                return {
                    "response": "",
                    "response_time": round(elapsed, 4),
                    "status_code": resp.status_code,
                    "error": resp.text,
                }
    except Exception as e:
        elapsed = time.perf_counter() - start
        return {
            "response": "",
            "response_time": round(elapsed, 4),
            "status_code": -1,
            "error": str(e),
        }


# ============================================================
# 테스트 실행
# ============================================================

def run_test(phase: str, count: int = 50):
    """
    지정된 phase로 count 회 API를 호출하고 결과를 저장합니다.
    """
    print(f"\n{'='*60}")
    print(f"  Phase: {phase.upper()} 프롬프트 | 총 {count}회 호출")
    print(f"  GPU Server: {GPU_SERVER_URL}")
    print(f"  NPC: {DEFAULT_NPC_ID}")
    print(f"  시작 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # 서버 상태 확인
    try:
        with httpx.Client(timeout=10.0) as client:
            health = client.get(f"{GPU_SERVER_URL}/health")
            if health.status_code == 200:
                info = health.json()
                print(f"✅ GPU 서버 연결 확인: {info.get('device', 'unknown')}")
                models = info.get("models", {})
                print(f"   - NPC Analyzer: {'✅' if models.get('npc_analyzer') else '❌'}")
                print(f"   - NPC LLM: {'✅' if models.get('npc_llm') else '❌'}")
            else:
                print(f"⚠️ GPU 서버 상태 비정상: {health.status_code}")
    except Exception as e:
        print(f"❌ GPU 서버 연결 실패: {e}")
        print("   서버가 실행 중인지 확인하세요.")
        return

    results = []
    errors = 0

    for i in range(count):
        msg = TEST_MESSAGES[i % len(TEST_MESSAGES)]
        print(f"  [{i+1:3d}/{count}] \"{msg[:20]}...\" ", end="", flush=True)

        result = call_npc_api(msg)
        result["call_index"] = i + 1
        result["input_message"] = msg

        if result["error"]:
            errors += 1
            print(f"❌ ({result['response_time']:.2f}s) {result['error'][:50]}")
        else:
            resp_preview = result["response"][:40].replace("\n", " ")
            print(f"✅ ({result['response_time']:.2f}s) \"{resp_preview}...\"")

        results.append(result)

    # 결과 저장
    os.makedirs(RESULTS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{phase}_{timestamp}.json"
    filepath = os.path.join(RESULTS_DIR, filename)

    output = {
        "phase": phase,
        "count": count,
        "npc_id": DEFAULT_NPC_ID,
        "gpu_server_url": GPU_SERVER_URL,
        "timestamp": datetime.now().isoformat(),
        "errors": errors,
        "results": results,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n📁 결과 저장: {filepath}")

    # 통계 출력
    print_stats(phase, results)

    return filepath


# ============================================================
# 통계 출력
# ============================================================

def print_stats(phase: str, results: list):
    """테스트 결과 통계 요약"""
    successful = [r for r in results if r["error"] is None]
    times = [r["response_time"] for r in successful]
    lengths = [len(r["response"]) for r in successful]

    print(f"\n{'='*60}")
    print(f"  📊 {phase.upper()} 프롬프트 결과 요약")
    print(f"{'='*60}")
    print(f"  총 호출: {len(results)}")
    print(f"  성공: {len(successful)}")
    print(f"  실패: {len(results) - len(successful)}")

    if times:
        print(f"\n  ⏱️  응답 시간 (초)")
        print(f"    평균:   {statistics.mean(times):.4f}")
        print(f"    중앙값: {statistics.median(times):.4f}")
        print(f"    최소:   {min(times):.4f}")
        print(f"    최대:   {max(times):.4f}")
        if len(times) >= 2:
            print(f"    표준편차: {statistics.stdev(times):.4f}")

    if lengths:
        print(f"\n  📝 응답 길이 (글자 수)")
        print(f"    평균:   {statistics.mean(lengths):.1f}")
        print(f"    중앙값: {statistics.median(lengths):.1f}")
        print(f"    최소:   {min(lengths)}")
        print(f"    최대:   {max(lengths)}")

    print(f"{'='*60}\n")


# ============================================================
# 결과 비교
# ============================================================

def compare_results():
    """영어/한국어 Phase 결과 파일을 비교합니다."""
    if not os.path.exists(RESULTS_DIR):
        print("❌ 결과 디렉토리가 없습니다. 먼저 테스트를 실행하세요.")
        return

    files = sorted(os.listdir(RESULTS_DIR))
    english_files = [f for f in files if f.startswith("english_") and f.endswith(".json")]
    korean_files = [f for f in files if f.startswith("korean_") and f.endswith(".json")]

    if not english_files:
        print("❌ 영어 프롬프트 결과 파일이 없습니다.")
        return
    if not korean_files:
        print("❌ 한국어 프롬프트 결과 파일이 없습니다.")
        return

    # 가장 최근 파일 사용
    en_path = os.path.join(RESULTS_DIR, english_files[-1])
    ko_path = os.path.join(RESULTS_DIR, korean_files[-1])

    print(f"\n📂 비교 대상:")
    print(f"  영어: {english_files[-1]}")
    print(f"  한국어: {korean_files[-1]}")

    with open(en_path, "r", encoding="utf-8") as f:
        en_data = json.load(f)
    with open(ko_path, "r", encoding="utf-8") as f:
        ko_data = json.load(f)

    en_results = [r for r in en_data["results"] if r["error"] is None]
    ko_results = [r for r in ko_data["results"] if r["error"] is None]

    en_times = [r["response_time"] for r in en_results]
    ko_times = [r["response_time"] for r in ko_results]
    en_lengths = [len(r["response"]) for r in en_results]
    ko_lengths = [len(r["response"]) for r in ko_results]

    print(f"\n{'='*70}")
    print(f"  📊 English vs Korean 비교 결과")
    print(f"{'='*70}")

    # 테이블 형태 출력
    header = f"{'항목':<20} {'English':>12} {'Korean':>12} {'차이':>12}"
    print(f"\n  {header}")
    print(f"  {'─'*56}")

    def row(label, en_val, ko_val, fmt=".4f"):
        diff = ko_val - en_val
        pct = (diff / en_val * 100) if en_val != 0 else 0
        sign = "+" if diff > 0 else ""
        print(f"  {label:<20} {en_val:>12{fmt}} {ko_val:>12{fmt}} {sign}{diff:>8{fmt}} ({sign}{pct:.1f}%)")

    if en_times and ko_times:
        print(f"\n  ⏱️  응답 시간 (초)")
        row("  평균", statistics.mean(en_times), statistics.mean(ko_times))
        row("  중앙값", statistics.median(en_times), statistics.median(ko_times))
        row("  최소", min(en_times), min(ko_times))
        row("  최대", max(en_times), max(ko_times))

    if en_lengths and ko_lengths:
        print(f"\n  📝 응답 길이 (글자)")
        row("  평균", statistics.mean(en_lengths), statistics.mean(ko_lengths), ".1f")
        row("  중앙값", statistics.median(en_lengths), statistics.median(ko_lengths), ".1f")
        row("  최소", float(min(en_lengths)), float(min(ko_lengths)), ".0f")
        row("  최대", float(max(en_lengths)), float(max(ko_lengths)), ".0f")

    print(f"\n  📈 성공률")
    en_success = len(en_results) / len(en_data["results"]) * 100 if en_data["results"] else 0
    ko_success = len(ko_results) / len(ko_data["results"]) * 100 if ko_data["results"] else 0
    print(f"    English: {en_success:.1f}% ({len(en_results)}/{len(en_data['results'])})")
    print(f"    Korean:  {ko_success:.1f}% ({len(ko_results)}/{len(ko_data['results'])})")

    print(f"\n{'='*70}")

    # 샘플 응답 비교 (같은 메시지에 대한 응답)
    print(f"\n  💬 동일 메시지 응답 비교 (첫 3개)")
    print(f"  {'─'*56}")
    for i in range(min(3, len(en_results), len(ko_results))):
        msg = en_results[i].get("input_message", "?")
        print(f"\n  [{i+1}] 입력: \"{msg}\"")
        en_resp = en_results[i]["response"][:80].replace("\n", " ")
        ko_resp = ko_results[i]["response"][:80].replace("\n", " ")
        print(f"      EN: \"{en_resp}...\"")
        print(f"      KO: \"{ko_resp}...\"")

    print()


# ============================================================
# main
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NPC 프롬프트 A/B 테스트")
    parser.add_argument(
        "--phase",
        choices=["english", "korean"],
        help="테스트 Phase (english 또는 korean)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=50,
        help="API 호출 횟수 (기본: 50)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="영어/한국어 결과 비교",
    )
    parser.add_argument(
        "--server",
        type=str,
        default=None,
        help="GPU 서버 URL (기본: http://localhost:8001)",
    )

    args = parser.parse_args()

    if args.server:
        GPU_SERVER_URL = args.server

    if args.compare:
        compare_results()
    elif args.phase:
        run_test(args.phase, args.count)
    else:
        parser.print_help()
        print("\n예시:")
        print("  python test_prompt_ab.py --phase english --count 50")
        print("  python test_prompt_ab.py --phase korean --count 50")
        print("  python test_prompt_ab.py --compare")
