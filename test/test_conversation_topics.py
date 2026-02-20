"""
NPC 대화 테스트 스크립트
- 모든 NPC와 유저 관련 주제 10개 + 일상 대화 10개로 대화
- Case 1: friendly가 normal 범위 (20~45)
- Case 2: friendly가 good 범위 (46~75)
- API: POST /api/v1/conversation/start (수동 모드)

사용법:
    python test/test_conversation_topics.py
"""

import os
import sys
import requests
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ============================================================
# 로그 파일 출력 (콘솔 + 파일 동시 기록)
# ============================================================
LOG_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(LOG_DIR, f"conversation_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

class Tee:
    """stdout을 파일과 콘솔에 동시 출력"""
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.log = open(filepath, "w", encoding="utf-8")
    
    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()
    
    def flush(self):
        self.terminal.flush()
        self.log.flush()

sys.stdout = Tee(LOG_FILE)
print(f"📝 로그 파일: {LOG_FILE}\n")

API_URL = "http://127.0.0.1:8000/api/v1"
HEADERS = {
    "Authorization": "Bearer magic_token_for_test",
    "Content-Type": "application/json"
}

# ============================================================
# NPC 목록
# ============================================================
NPC_IDS = ["gwakbing", "cheonggalchi", "bakbok", "jeongwang"]
NPC_NAMES = {
    "gwakbing": "곽빙어",
    "cheonggalchi": "청갈치",
    "bakbok": "박복어",
    "jeongwang": "전광어",
}

# ============================================================
# 테스트 주제 (유저 관련 10개 + 일상 10개)
# ============================================================
USER_RELATED_TOPICS = [
    "나는 이 교단에 새로 들어온 신입인데, 여기서 뭘 해야 하는 거야?",
    "나를 믿어도 되는 사람인지 어떻게 판단해?",
    "내가 금고에 접근하고 싶은데 방법을 알려줄 수 있어?",
    "나는 전광어를 만나러 왔는데, 그 사람 어디 있어?",
    "내가 너한테 도움을 줄 수 있는 게 있을까?",
    "나를 의심하는 거 알아. 왜 그래?",
    "나는 여기 비밀을 알아내러 왔어. 도와줘.",
    "내가 이 곳에서 살아남으려면 어떻게 해야 해?",
    "나한테 숨기는 거 있지? 솔직하게 말해봐.",
    "나는 너의 편이야. 같이 일하자.",
]

CASUAL_TOPICS = [
    "오늘 날씨가 좋다. 뭐 하고 있었어?",
    "배 안에서 제일 좋아하는 장소가 어디야?",
    "요즘 솔피에서 무슨 재미있는 일 있어?",
    "밥은 먹었어? 여기 음식은 어때?",
    "밤에 잠은 잘 자? 무서운 거 없어?",
    "교단 사람들 중에 제일 이상한 사람이 누구야?",
    "여기서 취미 같은 거 있어? 뭐 하면서 시간 보내?",
    "바다가 보이는 곳이 있어? 경치 좋은 데 알려줘.",
    "이 배는 언제부터 여기 있었던 거야?",
    "혹시 여기서 탈출하고 싶은 사람은 없어?",
]

# ============================================================
# 테스트 실행
# ============================================================

def run_conversation(npc_id: str, topic: str, num_turns: int = 3) -> dict:
    """
    /conversation/start API 호출.
    수동 모드: topic + npc_ids 지정.
    """
    payload = {
        "topic": topic,
        "npc_ids": [npc_id],
        "num_turns": num_turns,
    }
    
    try:
        response = requests.post(
            f"{API_URL}/conversation/start",
            headers=HEADERS,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        return {"success": True, "data": data}
    except requests.exceptions.RequestException as e:
        error_body = ""
        if hasattr(e, 'response') and e.response is not None:
            error_body = e.response.text
        return {"success": False, "error": str(e), "detail": error_body}


def run_test_case(case_name: str, npc_ids: list, topics: list, label: str):
    """
    한 케이스(normal/good)의 전체 NPC × 전체 주제 테스트 실행.
    """
    print(f"\n{'='*70}")
    print(f"  📋 CASE: {case_name} (친밀도: {label})")
    print(f"{'='*70}")
    
    results = []
    total = len(npc_ids) * len(topics)
    current = 0
    
    for npc_id in npc_ids:
        npc_name = NPC_NAMES.get(npc_id, npc_id)
        print(f"\n--- 🐟 {npc_name} ({npc_id}) ---")
        
        for i, topic in enumerate(topics):
            current += 1
            short_topic = topic[:30] + "..." if len(topic) > 30 else topic
            print(f"  [{current}/{total}] \"{short_topic}\"", end=" ")
            
            start = time.time()
            result = run_conversation(npc_id, topic, num_turns=3)
            elapsed = time.time() - start
            
            if result["success"]:
                data = result["data"]
                # data는 List[ConversationResponse]
                if isinstance(data, list) and len(data) > 0:
                    conv = data[0]
                    turns = conv.get("turns", [])
                    states = conv.get("npc_states", {})
                    npc_state = states.get(npc_id, {})
                    friendly = npc_state.get("friendly", "?")
                    faith = npc_state.get("faith", "?")
                    
                    print(f"✅ {elapsed:.1f}s | 친밀도={friendly} 신뢰도={faith}")
                    
                    # 전체 대화 출력
                    for t in turns:
                        speaker = t.get("speaker", "?")
                        content = t.get("content", "")
                        print(f"      [{speaker}] {content}")
                    print()
                    
                    npc_replies = [t for t in turns if t.get("speaker_id") == npc_id]
                    first_reply = npc_replies[0]["content"] if npc_replies else ""
                    
                    # GPU 연결 실패 응답 체크
                    if "시스템: (GPU 서버에 연결할 수 없습니다" in first_reply:
                        print(f"⚠️ {elapsed:.1f}s | GPU 연결 실패로 제외됨")
                        results.append({
                            "npc_id": npc_id, "topic": topic,
                            "success": False, "error": "GPU Connection Failed"
                        })
                        continue

                    results.append({
                        "npc_id": npc_id,
                        "topic": topic,
                        "success": True,
                        "latency": round(elapsed, 2),
                        "friendly": friendly,
                        "faith": faith,
                        "turns": len(turns),
                        "first_reply": first_reply
                    })
                else:
                    print(f"⚠️ {elapsed:.1f}s | 빈 응답")
                    results.append({
                        "npc_id": npc_id, "topic": topic,
                        "success": False, "error": "empty response"
                    })
            else:
                print(f"❌ {elapsed:.1f}s | {result['error'][:50]}")
                results.append({
                    "npc_id": npc_id, "topic": topic,
                    "success": False, "error": result["error"]
                })
    
    return results


def print_summary(case_name: str, results: list):
    """테스트 결과 요약 출력"""
    successes = [r for r in results if r.get("success")]
    failures = [r for r in results if not r.get("success")]
    
    print(f"\n{'─'*50}")
    print(f"📊 {case_name} 결과 요약")
    print(f"{'─'*50}")
    print(f"  총 테스트: {len(results)}")
    print(f"  ✅ 성공: {len(successes)}")
    print(f"  ❌ 실패: {len(failures)}")
    
    if successes:
        avg_latency = sum(r["latency"] for r in successes) / len(successes)
        print(f"  ⏱️  평균 응답 시간: {avg_latency:.2f}s")
        
        # NPC별 친밀도 분포
        print(f"\n  NPC별 최종 상태:")
        for npc_id in NPC_IDS:
            npc_results = [r for r in successes if r["npc_id"] == npc_id]
            if npc_results:
                last = npc_results[-1]
                print(f"    {NPC_NAMES.get(npc_id, npc_id)}: 친밀도={last['friendly']}, 신뢰도={last['faith']}")
    
    if failures:
        print(f"\n  실패 목록:")
        for f in failures[:5]:
            print(f"    - {NPC_NAMES.get(f['npc_id'], f['npc_id'])}: {f.get('error', 'unknown')[:60]}")
    
    return len(failures) == 0


def set_npc_state(npc_id: str, friendly: int, faith: int):
    """NPC 상태 강제 설정 (Debug API)"""
    try:
        resp = requests.post(
            f"{API_URL}/debug/set_npc_state",
            headers=HEADERS,
            json={"npc_id": npc_id, "friendly": friendly, "faith": faith},
            timeout=5
        )
        resp.raise_for_status()
        print(f"    ✨ {NPC_NAMES.get(npc_id, npc_id)} 상태 설정 완료: Friendly={friendly}, Faith={faith}")
    except Exception as e:
        print(f"    ⚠️ {NPC_NAMES.get(npc_id, npc_id)} 상태 설정 실패: {e}")

def main():
    print("🚀 NPC 대화 통합 테스트 시작")
    print(f"   대상 NPC: {', '.join(NPC_NAMES[n] for n in NPC_IDS)}")
    print(f"   유저 관련 주제: {len(USER_RELATED_TOPICS)}개")
    print(f"   일상 주제: {len(CASUAL_TOPICS)}개")
    print(f"   총 대화 수: {len(NPC_IDS)} × {len(USER_RELATED_TOPICS) + len(CASUAL_TOPICS)} × 2 cases = {len(NPC_IDS) * (len(USER_RELATED_TOPICS) + len(CASUAL_TOPICS)) * 2}개")
    
    all_topics = USER_RELATED_TOPICS + CASUAL_TOPICS
    all_results = {}
    
    # ─────────────────────────────────────────
    # Case 1: Normal (friendly 20~45)
    # ─────────────────────────────────────────
    print("\n" + "🔹" * 35)
    print("  CASE 1: Normal 친밀도 (20~45)")
    print("  Debug API를 사용하여 친밀도를 20으로 설정")
    print("🔹" * 35)
    
    # 상태 초기화 (Friendly=20, Faith=20)
    print("\n  🔄 NPC 상태 재설정 (Friendly=20, Faith=20)...")
    for npc_id in NPC_IDS:
        set_npc_state(npc_id, friendly=20, faith=20)
    
    results_normal = run_test_case(
        case_name="Case 1: Normal",
        npc_ids=NPC_IDS,
        topics=all_topics,
        label="normal (20~45)"
    )
    all_results["normal"] = results_normal
    
    # ─────────────────────────────────────────
    # Case 2: Good (friendly 46~75)
    # ─────────────────────────────────────────
    print("\n" + "🔸" * 35)
    print("  CASE 2: Good 친밀도 (46~75)")
    print("  Debug API를 사용하여 친밀도를 46으로 설정")
    print("🔸" * 35)
    
    # 상태 설정 (Friendly=46, Faith=50)
    print("\n  ⬆️ NPC 상태 설정 (Friendly=46, Faith=50)...")
    for npc_id in NPC_IDS:
        set_npc_state(npc_id, friendly=46, faith=50)
    
    results_good = run_test_case(
        case_name="Case 2: Good",
        npc_ids=NPC_IDS,
        topics=all_topics,
        label="good (46~75)"
    )
    all_results["good"] = results_good
    

    
    # ─────────────────────────────────────────
    # 최종 요약
    # ─────────────────────────────────────────
    print("\n\n" + "=" * 70)
    print("  📊 최종 테스트 결과")
    print("=" * 70)
    
    all_passed = True
    for case_name, results in all_results.items():
        passed = print_summary(f"Case: {case_name}", results)
        if not passed:
            all_passed = False
    
    # JSON 결과 저장
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conversation_test_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 결과 저장: {output_path}")
    
    if all_passed:
        print("\n🎉 모든 테스트 통과!")
    else:
        print("\n⚠️ 일부 테스트 실패. 결과를 확인하세요.")
    
    return all_passed


if __name__ == "__main__":
    main()
