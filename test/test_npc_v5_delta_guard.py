import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.npc_pipeline import NPCDialoguePipeline


def _make_pipeline_stub() -> NPCDialoguePipeline:
    # __init__ 우회: 테스트에선 helper 메서드만 사용
    return NPCDialoguePipeline.__new__(NPCDialoguePipeline)


def test_smalltalk_stabilize():
    p = _make_pipeline_stub()
    analysis = {
        "reason_tags": ["INCREASE_SUSPICION", "SHAKE_FAITH", "BUILD_TRUST"],
        "friendly_delta": -4,
        "faith_delta": -3,
    }
    out = p._stabilize_analysis("안녕 오늘 날씨 어때?", analysis)
    assert "INCREASE_SUSPICION" not in out["reason_tags"]
    assert "SHAKE_FAITH" not in out["reason_tags"]
    assert -1 <= out["friendly_delta"] <= 1
    assert out["faith_delta"] == 0
    print("✅ smalltalk delta guard")


def test_neutral_question_guard():
    p = _make_pipeline_stub()
    analysis = {
        "reason_tags": ["WITHDRAW_TRUST", "TEST_BOUNDARY", "BUILD_TRUST"],
        "friendly_delta": -3,
        "faith_delta": 0,
    }
    out = p._stabilize_analysis("여기 일과가 어떻게 돼?", analysis)
    assert "WITHDRAW_TRUST" not in out["reason_tags"]
    assert "TEST_BOUNDARY" not in out["reason_tags"]
    assert out["friendly_delta"] >= -1
    print("✅ neutral question guard")


if __name__ == "__main__":
    test_smalltalk_stabilize()
    test_neutral_question_guard()
