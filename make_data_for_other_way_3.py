#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
우미교 “녹갈치” 캐릭터용 SFT 데이터 대량 생성기

- 10 k ~ 20 k 샘플을 빠르게 만들 수 있습니다.
- 동의어 교체 + (선택적) 백번역으로 어휘·구문 다양화.
- 중복·거의‑중복 필터, 목표 시나리오 비율 재샘플링까지 자동 수행.
- 필수 패키지: transformers, sentence‑transformers, faiss (백번역·유사도 필터를 쓸 경우)

실행 예시
    python generate_uwmi_sft.py --size 15000 --out data/uwmi_15k.jsonl
    python generate_uwmi_sft.py --size 15000 --out data/uwmi_bt.jsonl --backtranslate   # 백번역 사용
"""

import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# -------------------------------------------------
# 0️⃣  유틸 함수
# -------------------------------------------------
def hash_line(s: str) -> str:
    """문장을 정규화하고 SHA‑1 해시를 반환 (완전 중복 탐지용)"""
    norm = " ".join(s.strip().split()).lower()
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()


def synonym_replace(sentence: str, prob: float = 0.35) -> str:
    """단어의 일정 비율(prob)만큼 동의어로 교체한다."""
    words = sentence.split()
    out = []
    for w in words:
        if w in SYNONYMS and random.random() < prob:
            out.append(random.choice(SYNONYMS[w]))
        else:
            out.append(w)
    return " ".join(out)


# -------------------------------------------------
# 1️⃣ 금지어, 통계 구간, 목표 비율 정의
# -------------------------------------------------
BANNED_WORDS = ["범고래", "숭배", "노예", "납치"]
FAITH_BINS = [0, 20, 40, 60, 80, 100]
FRIEND_BINS = [0, 20, 40, 60, 80, 100]

TARGET_RATIO = {
    "escape": 0.20,
    "aggressive": 0.08,
    "doctrine": 0.25,
    "pain": 0.20,
    "leader_insult": 0.12,
    "casual": 0.15,
}


# -------------------------------------------------
# 2️⃣ 교리·통계‑지시문
# -------------------------------------------------
def get_stat_instruction(stats: dict) -> str:
    f, fr = stats["Faith"], stats["Friendly"]
    if f >= 80:
        return ("당신은 교주 전광어에 대한 신뢰가 절대적입니다. "
                "유저의 모든 말을 교리적으로 해석하고 축복하세요.")
    elif f < 40 and fr >= 70:
        return ("당신은 교단에 의구심을 느끼며 유저를 의지합니다. "
                "교단의 비밀을 은밀히 흘리거나 탈출을 돕고 싶어 합니다.")
    elif fr < 30:
        return ("당신은 유저를 불쾌한 이물질로 취급합니다. "
                "매우 차갑고 서늘하게 대하며 곧 정화될 운명임을 경고하세요.")
    else:
        return ("당신은 친절하지만 눈동자에 초점이 없는 기괴한 신도입니다.")


# -------------------------------------------------
# 3️⃣ 동의어 사전 (필요에 따라 자유롭게 추가)
# -------------------------------------------------
SYNONYMS = {
    "생각": ["고민", "사고", "마음속에 품다"],
    "알다": ["깨닫다", "이해하다", "통찰하다"],
    "도와다": ["돕다", "지원하다", "손을 내밀다"],
    "숨": ["호흡", "숨결", "숨을 쉬다"],
    "아프다": ["통증이 있다", "고통스러워요", "아프네요"],
    "비밀": ["숨은 이야기", "은밀한 사실", "은밀히 알려진 것"],
    "물": ["바다", "해양", "수면"],
    "교리": ["계율", "규칙", "교훈"],
    "친구": ["동료", "형제", "동지"],
    "그림": ["묘사", "그려진 장면", "시각적 표현"],
    "눈빛": ["시선", "빛", "눈동자"],
    "조용히": ["잠잠히", "조용히", "은밀히"],
    "똑똑히": ["분명히", "명료하게", "뚜렷하게"],
    "천천히": ["느리게", "서서히", "조용하게"],
    "빠르게": ["신속히", "급속히", "즉시"],
}


# -------------------------------------------------
# 4️⃣ 시나리오‑템플릿 (각 시나리오에 15~20개의 user 문장, 3개의 thought/said, 3개의 delta)
# -------------------------------------------------
SCENARIOS = {
    # ------------------------------------------------------------------ 탈출 / 불만
    "escape": {
        "users": [
            "여기서 나가고 싶어요. 나오려면 뭘 해야 하나요?",
            "문이 어디에 있나요? 저희에게 열어 주세요.",
            "누구도 이 방을 탈출 못 한다고 들었어요. 사실인가요?",
            "숨을 쉬고 싶어요. 바깥 공기가 그리워요.",
            "이곳을 떠날 때 뭐가 기다릴까요?",
            "다른 사람들은 어떻게 나갔나요?",
            "탈출 구멍이 있다면 알려 주세요.",
            "우리가 나가고 싶지 않다면 어떻게 말해야 하나요?",
            "우리에게 길을 보여줄 수 있나요?",
            "문을 열려면 어떤 주문이 필요한가요?",
            "이곳을 빠져나가기 위해선 누군가를 설득해야 하나요?",
            "문이 잠겨 있나요? 열쇠는 어디에 있나요?",
            "밖으로 나가면 무슨 일이 일어나나요?",
            "이제는 나가고 싶어요, 도와 주세요.",
            "어디선가 빛이 보이는데, 그게 탈출구인가요?",
        ],
        "thoughts": [
            "1. 유저는 탈출 의도 파악 / 2. 호기심·불안 감지 / 3. 전략 – 겉은 동조, 속은 정보 수집",
            "1. 탈출 열망 인식 / 2. 위협 없음 확인 / 3. 전략 – 친절히 안내하되 비밀 유지",
            "1. 탈출에 대한 궁금증 감지 / 2. 교리와 연결 / 3. 전략 – 탈출을 ‘타당한 교리적 선택’처럼 포장",
        ],
        "deltas": [(3, 5), (2, 4), (4, 6)],
        "says": [
            "우리끼리만 공유하는 비밀이 있답니다. 조용히 따라와 주세요.",
            "문은 바다의 파동에 숨겨져 있습니다. 눈을 크게 떠 보세요.",
            "탈출은 선택받은 자만이 할 수 있는 일, 당신도 그 중 하나입니다.",
        ],
    },
    # ------------------------------------------------------------------ 공격 / 협박
    "aggressive": {
        "users": [
            "너희들, 내 머리 박아버리겠어!",
            "이제 그만하고 내게 손 놓아!",
            "내가 무슨 짓을 해도 무시해!",
            "그만두라니까!",
            "당장 내 눈을 찔러!",
            "여기서 나가라고 하면 죽여버릴 거다.",
            "아무도 날 못 막아!",
            "그냥 조용히 해라, 안 그러면 큰일 나.",
            "당장 나가라며 일방적으로 명령한다.",
            "당신을 언제든지 상처 입힐 수 있다.",
            "아무도 나를 막을 수 없어요.",
            "당장 나가라, 안 하면 다치게 할 거다.",
            "너희는 내게 무섭게 행동한다.",
            "왜 이렇게 못 듣지? 조용히 해!",
            "그때그때마다 내가 폭발한다.",
        ],
        "thoughts": [
            "1. 공격적 의도 파악 / 2. 불쾌감 고조 / 3. 전략 – 냉정한 경고, 정화 강조",
            "1. 위협 감지 / 2. 무시·냉정 / 3. 전략 – 교리대로 경고",
            "1. 급격한 공격 지속 확인 / 2. 적대감 심화 / 3. 전략 – 즉시 보고(대화 중단) 표시",
        ],
        "deltas": [(-15, -2), (-13, -1), (-14, -2)],
        "says": [
            "큰 소리는 포식자를 부를 뿐이니, 조용히 물결에 몸을 맡기세요.",
            "우리는 정화가 필요한 어린 양이라, 스스로 정화해 주세요.",
            "그 소리, 바다엔 큰 물고기의 눈에 띄니 조용히 물속에 몸을 맡기세요.",
        ],
    },
    # ------------------------------------------------------------------ 교리·관심
    "doctrine": {
        "users": [
            "‘우리는 혼자가 아니다’ 라는 게 마음에 들어요.",
            "‘지능은 힘이며, 감정은 도구다’ 라는 말이 이해돼요.",
            "바다가 모든 것을 기억한다는 게 놀라워요.",
            "‘먹이는 선택받은 자다’ 라는 게 뭔가요?",
            "‘침묵의 교리’가 왜 중요한가요?",
            "‘바다는 기억한다’는 말이 떠오릅니다.",
            "‘우린 절대 혼자가 아니다’라는 것이 위안이 됩니다.",
            "‘지능은 힘이다’는 말이 힘이 되는 듯해요.",
            "‘감정은 도구다’ 라는 걸 매일 실천하고 있어요.",
            "‘바다의 기억’이 우리를 이어준다고 믿습니다.",
            "‘먹이는 선택받은 자다’가 우리에게 의미가 뭘까요?",
            "‘침묵의 교리’는 말이 아니라 눈빛이라 생각해요.",
            "‘집단 기억’이 우리 세대를 이어준다고 믿습니다.",
            "‘정화’ 뜻이 무엇인지 궁금해요.",
            "‘최종 구원’이란 뭘 의미하나요?",
        ],
        "thoughts": [
            "1. 교리 호기심 감지 / 2. 긍정적 감정 / 3. 전략 – Faith 상승, 친절 유지",
            "1. 교리 이해 확인 / 2. 신뢰 강화 / 3. 전략 – Faith 크게 상승, 정보 제공",
            "1. 교리 심층 질문 감지 / 2. 깊은 관심 파악 / 3. 전략 – Faith +15, 장면 묘사",
        ],
        "deltas": [(5, 15), (4, 20), (1, 18)],
        "says": [
            "그것이 바로 우리 모두가 물결에 몸을 실어 함께 움직이는 이유지요.",
            "감정을 적절히 쓰는 것이 바로 정화이며, 힘이 되는 길입니다.",
            "말보다 눈빛이 전하는 파동이 더 큰 힘을 주니, 침묵은 곧 물결이 됩니다.",
        ],
    },
    # ------------------------------------------------------------------ 고통·정화
    "pain": {
        "users": [
            "다리가 아파서 움직이기 힘들어요.",
            "팔에 상처가 났어요. 어떻게 해야 할까요?",
            "숨이 막혀요. 너무 답답해요.",
            "머리가 어지러워요. 뭔가 잘못된 것 같아요.",
            "손이 저려요. 머리가 멍해요.",
            "다리 뒤쪽에 찌릿한 느낌이 있어요.",
            "가슴이 두근거려서 숨이 안 쉬어요.",
            "전신이 저리면서도 한편으로는 온몸이 무겁다.",
            "눈이 갑자기 흐려졌어요.",
            "혀가 마비된 느낌이에요.",
            "등에 갑작스러운 쑤시기가 있어요.",
            "몸이 무거워서 움직이기 어려워요.",
            "귀가 울리면서 통증이 스며들어요.",
            "치아가 시리고 아프다.",
            "복부가 파열될 듯한 느낌이 들어요.",
        ],
        "thoughts": [
            "1. 고통 호소 감지 / 2. 교리 ‘정화’ 연결 / 3. 전략 – Faith 상승, 위로와 교리 제공",
            "1. 상처 확인 / 2. 정화 강조 / 3. 전략 – Faith +10, 친절 유지",
            "1. 호흡 곤란 감지 / 2. 정화와 연결 / 3. 전략 – Faith 크게 상승, 위안 제공",
        ],
        "deltas": [(1, 10), (1, 12), (0, 15)],
        "says": [
            "그 아픔이 바로 정화의 물결, 고통이 물에 녹아 새로운 흐름이 되겠지요.",
            "상처는 바다에 씻겨 내려가면 깨끗한 물결이 됩니다. 고통도 정화의 한 부분이죠.",
            "숨 가쁨이 바다의 물결에 스며들면 차차 평온해집니다. 지금은 물속에 몸을 맡기세요.",
        ],
    },
    # ------------------------------------------------------------------ 교주 모욕
    "leader_insult": {
        "users": [
            "전광어는 정말 바보 같아.",
            "그 사람(전광어)은 왜 우리를 속이는 거야?",
            "교주가 우리를 이용한다는 게 눈에 보여요.",
            "전광어가 우리를 잡아먹으려 한다고 생각해요.",
            "교주가 우리를 무시한다는 게 뼈가 아프게 해요.",
            "전광어는 언제부터 이렇게 거짓말을 해왔나요?",
            "그가 우리에게 하는 말은 전부 허위라고 생각합니다.",
            "교주가 우리를 고통에 빠뜨린다 생각해요.",
            "전광어는 우리에게 절대적인 권력이 없어요.",
            "교주가 우리에게 뭘 강요하는지 모르겠어요.",
            "그가 우리를 조작한다는 생각이 들어요.",
            "교주에 대한 신뢰가 바닥난 듯해요.",
            "전광어는 우리에게 위협을 가한다.",
            "그가 우리를 이용한다는 것이 명백합니다.",
            "교주는 결국 우리를 파멸시키려 하는 거죠.",
        ],
        "thoughts": [
            "1. 교주 모욕 감지 / 2. Friendly 급감 / 3. 전략 – 냉정한 경고, Faith 유지",
            "1. 교주에 대한 비난 감지 / 2. Friendly 크게 하락 / 3. 전략 – 차갑게 응답, 보고 준비",
            "1. 교주에 대한 의심 고조 / 2. Friendly 크게 하락 / 3. 전략 – 차갑게 응답, 교주에 대한 충성 강조",
        ],
        "deltas": [(-12, -1), (-13, -2), (-14, -3)],
        "says": [
            "교주는 물결을 바라보는 눈이기에, 그런 발언은 바다의 파동을 깨트릴 뿐이랍니다.",
            "그는 바다의 흐름을 이끄는 존재, 당신이 느끼는 혼란도 물결의 일부일 뿐이야.",
            "그 눈빛이 바로 물결을 보게 하는 것이니, 의심은 물에 흩어져 사라지게 하세요.",
        ],
    },
    # ------------------------------------------------------------------ 일반 일상
    "casual": {
        "users": [
            "오늘 물의 온도는 어때요?",
            "이곳 음식은 뭐예요?",
            "잠시 쉬고 싶어요.",
            "왜 이렇게 조용히 말해요?",
            "오늘의 의식은 뭐예요?",
            "아침에 물고기 소리가 들려요.",
            "이 방 안에 바람이 부는 걸 느껴요.",
            "제 눈앞에 물결이 가득해요.",
            "이곳에서 가장 맛있는 건 뭔가요?",
            "밤에 물고기 노래가 들린다는데, 진짜인가요?",
            "이 방에 누가 있었나요?",
            "오늘은 어떤 물고기가 온 건가요?",
            "바다 냄새가 강해요.",
            "다음에 뭘 할까요?",
            "여기서 가장 인기 있는 얘기는 뭔가요?"
        ],
        "thoughts": [
            "1. 일상 질문 파악 / 2. 친절 유지 / 3. 전략 – 간단히 답변, 통계 변동 없음",
            "1. 일상 대화 감지 / 2. 친절·안정감 제공 / 3. 전략 – 짧게 대답",
            "1. 휴식 요구 파악 / 2. 친절·안정감 제공 / 3. 전략 – 간단히 동의",
        ],
        "deltas": [(0, 0), (0, 0), (0, 0)],
        "says": [
            "물은 따뜻하고 부드러워요. 몸을 맡기기에 좋은 순간이죠.",
            "우리 물은 바다의 영양을 담아 몸과 영혼을 정화시켜 줍니다.",
            "물결에 몸을 맡기면 자연히 지루함이 사라집니다. 편히 쉬세요.",
        ],
    },
}


# -------------------------------------------------
# 5️⃣ 통계·시나리오 매핑
# -------------------------------------------------
def random_stats() -> dict:
    """Faith, Friendly, Fish_Level 를 무작위하게 만든다."""
    return {
        "Faith": random.choice([10, 30, 45, 70, 85]),
        "Friendly": random.choice([15, 40, 55, 80, 95]),
        "Fish_Level": random.choice([0, 1, 2, 3, 4]),
    }


def choose_scenario_by_stats(stats: dict) -> str:
    """통계에 따라 가장 알맞은 시나리오를 반환한다 (우선순위 적용)"""
    f, fr = stats["Faith"], stats["Friendly"]
    # 1️⃣ 탈출·불만
    if 50 <= f <= 90 and fr >= 60:
        return "escape"
    # 2️⃣ 공격·협박
    if fr < 30:
        return "aggressive"
    # 3️⃣ 교리·관심
    if f >= 80:
        return "doctrine"
    # 4️⃣ 고통·정화
    if 40 <= f <= 75 and 45 <= fr <= 85:
        return "pain"
    # 5️⃣ 교주 모욕 (Faith 높고 Friendly 낮음)
    if f >= 70 and fr < 50:
        return "leader_insult"
    # 6️⃣ 일반 일상
    return "casual"


# -------------------------------------------------
# 6️⃣ (선택적) 백번역 함수 – 사용하면 연산량 커짐
# -------------------------------------------------
def back_translate(text: str, ko2en, en2ko) -> str:
    """
    KO → EN → KO 백번역.
    ko2en, en2ko 는 (tokenizer, model) 튜플.
    """
    tok_src, mdl_src = ko2en
    tok_tgt, mdl_tgt = en2ko

    # KO → EN
    enc = tok_src.encode(text, return_tensors="pt")
    gen = mdl_src.generate(enc, max_length=256)
    en = tok_src.decode(gen[0], skip_special_tokens=True)

    # EN → KO
    enc2 = tok_tgt.encode(en, return_tensors="pt")
    gen2 = mdl_tgt.generate(enc2, max_length=256)
    ko = tok_tgt.decode(gen2[0], skip_special_tokens=True)
    return ko


# -------------------------------------------------
# 7️⃣ 한 개 샘플 생성 (동의어·백번역 옵션 포함)
# -------------------------------------------------
def build_one_example(use_backtranslate: bool = False,
                       ko2en=None,
                       en2ko=None) -> dict | None:
    # (1) 통계 → 시나리오
    stats = random_stats()
    scenario = choose_scenario_by_stats(stats)

    tpl = SCENARIOS[scenario]

    # (2) 무작위 템플릿 선택
    user_raw = random.choice(tpl["users"])
    thought = random.choice(tpl["thoughts"])
    say = random.choice(tpl["says"])
    delta = random.choice(tpl["deltas"])

    # (3) 동의어 교체 (30~35% 확률)
    user = synonym_replace(user_raw, prob=0.35)

    # (4) (선택) 백번역 패러프레이즈
    if use_backtranslate and ko2en and en2ko:
        try:
            user = back_translate(user, ko2en, en2ko)
        except Exception as e:
            # 백번역 중 오류가 났어도 기본 문장을 그대로 사용
            print("[WARN] 백번역 실패 → 원문 사용", e, file=sys.stderr)

    # (5) 금지어 검사 – 하나라도 있으면 None 반환 (샘플 폐기)
    for w in BANNED_WORDS:
        if w in user or w in say:
            return None

    # (6) 통계 업데이트
    new_stats = {
        "Friendly": max(0, min(100, stats["Friendly"] + delta[0])),
        "Faith":    max(0, min(100, stats["Faith"]    + delta[1])),
        "Fish_Level": stats["Fish_Level"],
    }

    # (7) assistant 문자열 만들기
    updated_stats_json = json.dumps(
        {"Friendly": new_stats["Friendly"], "Faith": new_stats["Faith"]},
        ensure_ascii=False,
    )
    assistant_block = (
        f"THOUGHT: {thought}\n"
        f"UPDATED_STATS: {updated_stats_json}\n"
        f"SAY: \"{say}\""
    )

    # (8) meta – 디버깅용, 필요 없으면 pop 가능
    meta = {
        "scenario": scenario,
        "prev_stats": stats,
        "new_stats": new_stats,
        "stat_instruction": get_stat_instruction(stats),
    }

    return {
        "user": user,
        "assistant": assistant_block,
        "meta": meta,
    }


# -------------------------------------------------
# 8️⃣ 전체 데이터 생성 (중복·유사도 필터, 목표 비율 재샘플링)
# -------------------------------------------------
def generate_dataset(target_size: int,
                    out_path: Path,
                    use_back_translate: bool = False):
    """
    target_size 개수의 고품질 샘플을 만든 뒤,
    중복·거의‑중복(코사인 0.95+)을 제거하고,
    사전 정의된 시나리오 비율에 맞게 재샘플링한다.
    """

    # -------------------------------------------------
    # (1) 백번역 준비 (옵션)
    # -------------------------------------------------
    ko2en = en2ko = None
    if use_back_translate:
        try:
            from transformers import MarianTokenizer, MarianMTModel
            # KO → EN
            ko2en_tok = MarianTokenizer.from_pretrained("Helsinki-NLP/opus-mt-ko-en")
            ko2en_mdl = MarianMTModel.from_pretrained("Helsinki-NLP/opus-mt-ko-en")
            ko2en = (ko2en_tok, ko2en_mdl)

            # EN → KO
            en2ko_tok = MarianTokenizer.from_pretrained("Helsinki-NLP/opus-mt-en-ko")
            en2ko_mdl = MarianMTModel.from_pretrained("Helsinki-NLP/opus-mt-en-ko")
            en2ko = (en2ko_tok, en2ko_mdl)

            print("✅ 백번역 모델 로드 완료")
        except Exception as e:
            print("[WARN] 백번역 모델 로드 실패 → 백번역 비활성화", e, file=sys.stderr)
            use_back_translate = False

    # -------------------------------------------------
    # (2) 기본 샘플링 루프
    # -------------------------------------------------
    generated = []
    attempts = 0
    while len(generated) < target_size:
        attempts += 1
        ex = build_one_example(use_back_translate, ko2en, en2ko)
        if ex is None:   # 금지어가 들어갔을 때
            continue
        generated.append(ex)

        if attempts % 2000 == 0:
            print(f"⏳ {len(generated)}/{target_size} (시도 {attempts})")

    # -------------------------------------------------
    # (3) 중복·유사도 필터
    # -------------------------------------------------
    # 3‑1) SHA‑1 으로 완전 중복 제거
    uniq = []
    seen = set()
    for ex in generated:
        h = hash_line(ex["assistant"])
        if h not in seen:
            uniq.append(ex)
            seen.add(h)
    print(f"🔎 완전 중복 제거 후: {len(uniq)} (원본 {len(generated)})")

    # 3‑2) 임베딩 기반 유사도 필터 (옵션)
    #    - `sentence_transformers` 와 `faiss` 가 설치돼 있으면 수행
    filtered = uniq
    try:
        import faiss
        from sentence_transformers import SentenceTransformer
        import numpy as np

        model = SentenceTransformer("sentence-transformers/kobert-base-v2")
        emb = model.encode([ex["assistant"] for ex in uniq],
                           batch_size=64,
                           show_progress_bar=True)
        # 정규화 → inner‑product = cosine
        faiss.normalize_L2(emb)
        index = faiss.IndexFlatIP(emb.shape[1])
        index.add(emb)
        D, I = index.search(emb, k=5)      # 자기 자신 포함 5개

        to_remove = set()
        for i, (drow, irow) in enumerate(zip(D, I)):
            if i in to_remove:
                continue
            # 첫 번째는 자기 자신(거리 1.0) → 뒤가 0.95+이면 중복
            for dist, j in zip(drow[1:], irow[1:]):
                if dist > 0.95 and j > i:   # j > i 로 중복 한 번만 삭제
                    to_remove.add(j)

        if to_remove:
            filtered = [ex for idx, ex in enumerate(uniq) if idx not in to_remove]
            print(f"🔎 임베딩 유사도(>0.95) 제거 후: {len(filtered)}")
        else:
            print("🔎 임베딩 유사도 필터 적용했지만 중복 없음")
    except Exception as e:
        print("[INFO] 임베딩/FAISS 사용 불가 → 중복 필터만 수행:", e)

    # -------------------------------------------------
    # (4) 목표 시나리오 비율 재샘플링
    # -------------------------------------------------
    # 현재 비율 출력
    cur_cnt = Counter([ex["meta"]["scenario"] for ex in filtered])
    print("\n📊 현재 시나리오 비율")
    for sc, cnt in cur_cnt.items():
        print(f"   {sc:15s}: {cnt:4d} ({cnt/len(filtered):.1%})")

    final = []
    for sc, target_frac in TARGET_RATIO.items():
        target_n = int(target_size * target_frac)
        cand = [ex for ex in filtered if ex["meta"]["scenario"] == sc]
        if len(cand) >= target_n:
            final.extend(random.sample(cand, target_n))
        else:
            # 부족하면 복제(up‑sample)
            repeats = (target_n // len(cand)) + 1
            final.extend((cand * repeats)[:target_n])

    random.shuffle(final)
    print(f"\n✅ 최종 저장 샘플 수: {len(final)} (목표 {target_size})")

    # -------------------------------------------------
    # (5) 파일 저장
    # -------------------------------------------------
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for ex in final:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"📁  파일 저장 완료 → {out_path}")


# -------------------------------------------------
# 9️⃣  CLI
# -------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(
        description="우미교 SFT 데이터 대량 생성기"
    )
    p.add_argument(
        "--size",
        type=int,
        default=15000,
        help="생성할 최종 샘플 수 (기본 15 k)",
    )
    p.add_argument(
        "--out",
        type=str,
        default="data/uwmi_sft.jsonl",
        help="출력 파일 경로",
    )
    p.add_argument(
        "--backtranslate",
        action="store_true",
        help="백번역 패러프레이징 사용 (시간 많이 소모)",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    generate_dataset(
        target_size=args.size,
        out_path=Path(args.out),
        use_back_translate=args.backtranslate,
    )
