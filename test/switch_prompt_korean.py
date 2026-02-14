"""
한국어 프롬프트 전환 스크립트
- Phase 2 실행 전에 이 스크립트를 실행하면 프롬프트를 한국어로 변경합니다.
- Phase 1으로 되돌리려면 --revert 옵션을 사용하세요.

사용법:
    python switch_prompt_korean.py          # 한국어로 전환
    python switch_prompt_korean.py --revert  # 영어로 복원
"""

import os
import sys
import argparse
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PIPELINE_PATH = os.path.join(BASE_DIR, "app", "agents", "npc_pipeline.py")
ENGINE_PATH = os.path.join(BASE_DIR, "app", "agents", "npc_dialogue_engine.py")
BACKUP_SUFFIX = ".backup_en"


def backup_files():
    """원본 영어 파일 백업"""
    for path in [PIPELINE_PATH, ENGINE_PATH]:
        backup = path + BACKUP_SUFFIX
        if not os.path.exists(backup):
            shutil.copy2(path, backup)
            print(f"  📦 백업: {os.path.basename(path)} → {os.path.basename(backup)}")
        else:
            print(f"  ℹ️ 백업 이미 존재: {os.path.basename(backup)}")


def switch_to_korean():
    """프롬프트를 한국어로 전환"""
    print("\n🔄 프롬프트를 한국어로 전환합니다...\n")
    backup_files()

    # 1. npc_pipeline.py 수정
    with open(PIPELINE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # _build_system_prompt 내부 변경
    replacements_pipeline = [
        # BASIC_SETTING
        (
            '[BASIC_SETTING]\\nYou are {korean_name} ({self.npc_id}). Converse according to the given situation.',
            '[기본_설정]\\n당신은 {korean_name} ({self.npc_id})입니다. 주어진 상황에 맞게 대화하세요.',
        ),
        # RETRIEVED_INFO
        (
            '[RETRIEVED_INFO (Persona/Memory)]',
            '[검색_정보 (페르소나/기억)]',
        ),
        # CURRENT_RELATIONSHIP
        (
            '[CURRENT_RELATIONSHIP]',
            '[현재_관계]',
        ),
        (
            '- Friendly: {self.state.friendly}/100',
            '- 호감도: {self.state.friendly}/100',
        ),
        (
            '- Faith: {self.state.faith}/100',
            '- 신뢰도: {self.state.faith}/100',
        ),
        # OUTPUT_RULES
        (
            '[OUTPUT_RULES]',
            '[출력_규칙]',
        ),
        (
            "- Output ONLY {korean_name}'s dialogue.",
            "- {korean_name}의 대사만 출력하세요.",
        ),
        (
            '- MUST SPEAK IN KOREAN.',
            '- 반드시 한국어로 말하세요.',
        ),
        (
            '- NO options, explanations, summaries, markdown, or code blocks.',
            '- 선택지, 설명, 요약, 마크다운, 코드 블록을 사용하지 마세요.',
        ),
        (
            '- End the last sentence with a counter-question, suggestion, or implying next action.',
            '- 마지막 문장은 되묻기, 제안, 또는 다음 행동을 암시하는 것으로 끝내세요.',
        ),
    ]

    for old, new in replacements_pipeline:
        if old in content:
            content = content.replace(old, new)
        else:
            print(f"  ⚠️ 찾을 수 없음 (pipeline): {old[:50]}...")

    with open(PIPELINE_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  ✅ {os.path.basename(PIPELINE_PATH)} → 한국어 전환 완료")

    # 2. npc_dialogue_engine.py 수정
    with open(ENGINE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    replacements_engine = [
        (
            '[CONTROL_SIGNAL]',
            '[제어_신호]',
        ),
        (
            'REASON_TAGS: {tag_str}',
            '이유_태그: {tag_str}',
        ),
        (
            'PREDICTED_DELTA: friendly={friendly_delta:+d}, faith={faith_delta:+d}',
            '예측_변화: 호감도={friendly_delta:+d}, 신뢰도={faith_delta:+d}',
        ),
        (
            'ACTION_GUIDE:',
            '행동_지침:',
        ),
        (
            '- WITHDRAW_TRUST detected: Strengthen vigilance, distance yourself, question back more.',
            '- WITHDRAW_TRUST 감지: 경계를 강화하고 거리를 두며 더 많이 되물으세요.',
        ),
        (
            '- BUILD_TRUST detected: Open up to cooperation, consider sharing information.',
            '- BUILD_TRUST 감지: 협력에 열린 자세를 취하고 정보 공유를 고려하세요.',
        ),
        (
            '- DEFLECT/GASLIGHT: Avoid direct answers, speak evasively or metaphorically.',
            '- DEFLECT/GASLIGHT: 직접적 답변을 피하고 돌려 말하거나 은유적으로 말하세요.',
        ),
        (
            "- TEST_BOUNDARY: Try to determine the other's hidden intent.",
            '- TEST_BOUNDARY: 상대의 숨겨진 의도를 파악하려 하세요.',
        ),
        (
            '- PROTECT_SECRET/PROTECT_DOCTRINE: Hide core truth, give only vague hints.',
            '- PROTECT_SECRET/PROTECT_DOCTRINE: 핵심 진실을 숨기고 모호한 힌트만 주세요.',
        ),
        (
            '- INCREASE_SUSPICION: Be wary of suspicious questions.',
            '- INCREASE_SUSPICION: 의심스러운 질문에 경계하세요.',
        ),
        (
            '- REDUCE_SUSPICION: Detect attempts to build rapport.',
            '- REDUCE_SUSPICION: 친밀감을 쌓으려는 시도를 감지하세요.',
        ),
    ]

    for old, new in replacements_engine:
        if old in content:
            content = content.replace(old, new)
        else:
            print(f"  ⚠️ 찾을 수 없음 (engine): {old[:50]}...")

    with open(ENGINE_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  ✅ {os.path.basename(ENGINE_PATH)} → 한국어 전환 완료")

    print("\n✅ 한국어 프롬프트 전환 완료!")
    print("⚠️  GPU 서버를 재시작해야 변경 사항이 적용됩니다.\n")


def revert_to_english():
    """영어 프롬프트로 복원"""
    print("\n🔄 영어 프롬프트로 복원합니다...\n")

    for path in [PIPELINE_PATH, ENGINE_PATH]:
        backup = path + BACKUP_SUFFIX
        if os.path.exists(backup):
            shutil.copy2(backup, path)
            os.remove(backup)
            print(f"  ✅ {os.path.basename(path)} → 영어 복원 완료")
        else:
            print(f"  ⚠️ 백업 파일 없음: {os.path.basename(backup)}")

    print("\n✅ 영어 프롬프트 복원 완료!")
    print("⚠️  GPU 서버를 재시작해야 변경 사항이 적용됩니다.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="프롬프트 언어 전환")
    parser.add_argument("--revert", action="store_true", help="영어 프롬프트로 복원")
    args = parser.parse_args()

    if args.revert:
        revert_to_english()
    else:
        switch_to_korean()
