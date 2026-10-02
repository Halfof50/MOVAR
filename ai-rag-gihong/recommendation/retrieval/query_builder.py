"""
검색 Query 생성

비전 모델 출력(증상 6종 × 0~3)을 검색용 자연어 문장으로 바꾼다.
입력 형식이 고정이므로 LLM 을 호출하지 않고 규칙으로 만든다.

심각도가 높은 증상이 문장 앞에 오고 '우선' 표현을 받는다.
임베딩은 문장 전체를 하나의 벡터로 만들기 때문에
앞에 오는 표현과 반복되는 표현이 벡터 방향에 더 크게 반영된다.
"""

from recommendation.config import SYMPTOMS, SYMPTOM_KR


def _has_jongseong(word: str) -> bool:
    """마지막 글자에 종성이 있는지. 조사 선택에 쓴다."""
    if not word:
        return False
    ch = word[-1]
    if not ("가" <= ch <= "힣"):
        return False
    return (ord(ch) - 0xAC00) % 28 != 0


def josa_iga(word: str) -> str:
    return "이" if _has_jongseong(word) else "가"


def josa_eulreul(word: str) -> str:
    return "을" if _has_jongseong(word) else "를"


# 증상별 검색 문구. 상품 Document 의 '관리 목적' 표현과 짝을 맞춘다.
QUERY_TEXT = {
    "micro_keratin":       "두피 각질 관리",
    "excess_sebum":        "과도한 피지와 유분 관리",
    "follicular_erythema": "붉어진 두피와 자극 진정",
    "follicular_pustule":  "두피 트러블 및 농포 관리",
    "dandruff":            "비듬 관리",
    "hair_loss":           "탈모 증상 완화와 모발 및 두피 관리",
}

# 레벨별 서술.
# md §6.2 예시가 2단계 "주요 관리가 필요하며", 1단계 "경미하게 나타난" 으로 적고 있다.
# 문장 중간에 오면 연결형(MID), 마지막에 오면 '두피' 를 수식하는 관형형(END) 을 쓴다.
# 3단계 표현은 md 예시에 없어서, 2단계 표현을 한 단계 올려 맞췄다.
LEVEL_MID = {
    3: "집중 관리가 필요하며",
    2: "주요 관리가 필요하며",
    1: "경미하게 나타나며",
}
LEVEL_END = {
    3: "집중 관리가 필요한",
    2: "주요 관리가 필요한",
    1: "경미하게 나타난",
}

NO_SYMPTOM_QUERY = (
    "두피에 특별한 증상이 없는 상태. "
    "자극이 적고 두피와 모발을 일상적으로 관리하는 순한 제품."
)


def normalize_levels(symptoms: dict) -> dict:
    """{'dandruff': 1, ...} 또는 {'dandruff': {'level': 1}, ...} → {'dandruff': 1, ...}"""
    out = {}
    for key in SYMPTOMS:
        v = symptoms.get(key, 0)
        if isinstance(v, dict):
            v = v.get("level", 0)
        try:
            v = int(v)
        except (TypeError, ValueError):
            v = 0
        out[key] = max(0, min(3, v))
    return out


def ranked_symptoms(levels: dict) -> list:
    """레벨이 1 이상인 증상을 레벨 높은 순으로. 동일 레벨은 SYMPTOMS 순서 유지."""
    active = [s for s in SYMPTOMS if levels.get(s, 0) > 0]
    return sorted(active, key=lambda s: (-levels[s], SYMPTOMS.index(s)))


def build_query(symptoms: dict) -> str:
    """증상 레벨 → 검색 Query 문장"""
    levels = normalize_levels(symptoms)
    ranked = ranked_symptoms(levels)

    if not ranked:
        return NO_SYMPTOM_QUERY

    # 1문장: 상태 서술. 심한 증상이 앞에 온다.
    # 가장 심한 증상만 '증상이' 를 붙이고 나머지는 조사만 붙인다.
    clauses = []
    for i, s in enumerate(ranked):
        kr = SYMPTOM_KR[s]
        subject = f"{kr} 증상이" if i == 0 else f"{kr}{josa_iga(kr)}"
        last = (i == len(ranked) - 1)
        phrase = LEVEL_END[levels[s]] if last else LEVEL_MID[levels[s]]
        clauses.append(f"{subject} {levels[s]}단계로 {phrase}")
    state = ", ".join(clauses) + " 두피."

    # 2문장: 원하는 제품 서술. 가장 심한 증상을 '우선'으로 둔다.
    top, rest = ranked[0], ranked[1:]
    head = QUERY_TEXT[top]
    if rest:
        tail = ", ".join(QUERY_TEXT[s] for s in rest)
        want = (f"{head}{josa_eulreul(head)} 우선하면서 "
                f"{tail}에도 적합한 두피 케어 제품.")
    else:
        want = f"{head}에 적합한 두피 케어 제품."

    return f"{state} {want}"


if __name__ == "__main__":
    cases = {
        "비듬1 탈모2":   {"dandruff": 1, "hair_loss": 2},
        "각질3 피지2":   {"micro_keratin": 3, "excess_sebum": 2},
        "홍반2 농포2 비듬1": {"follicular_erythema": 2, "follicular_pustule": 2, "dandruff": 1},
        "전부 0":        {},
    }
    for label, s in cases.items():
        print(f"[{label}]")
        print(build_query(s))
        print()
