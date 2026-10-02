"""
순한 정도 계산

증상이 모두 0단계인 사용자에게 쓰는 기준이다.
증상이 없으면 '어떤 증상에 맞는가' 로 고를 수 없으니 '자극 요인이 적은가' 로 고른다.

판정 축 4개. 각 축이 없으면 1점, 전부 없으면 4.0 이다.
    설페이트 계면활성제
    향료
    에탄올·변성알코올
    각질제거 산

축을 고른 근거 (데이터 146개 실측)
    설페이트    샴푸 55/83 포함 → 28개가 무첨가. 변별력이 가장 좋다
    향료        샴푸 69/83 포함 → 14개가 무첨가
    에탄올      샴푸 34/83 포함
    각질제거 산  샴푸 53/83 포함. 증상이 0단계면 각질을 벗길 이유가 없다
파라벤은 146개 중 1개뿐이라 넣지 않았다. 변별이 안 된다.

전체 문자열 검색을 쓰지 않는 이유.
    '에탄올' 로 찾으면 페녹시에탄올(보존제) 25건이 걸린다.
    '알코올' 로 찾으면 세틸·스테아릴알코올(유연제) 이 걸린다. 둘 다 자극원이 아니다.
    그래서 토큰으로 끊고, 자극원 목록과 제외 목록을 따로 둔다.

표현은 사실 표기로만 쓴다.
    '설페이트 무첨가' 는 전성분에서 확인되는 사실이다.
    '자극이 적다' 는 효능 주장에 가까워 쓰지 않는다.
"""

from recommendation.preprocessing.ingredient_normalizer import (
    match_canonical, split_ingredients,
)

# 토큰 안에 이 문자열이 있으면 해당 축에 걸린다
SULFATE_KEYS = ["라우릴설페이트", "라우레스설페이트", "도데실벤젠설포네이트"]

# 토큰 전체가 이 이름과 같아야 걸린다. 부분 일치로는 잡지 않는다.
FRAGRANCE_EXACT = ["향료", "착향제", "퍼퓸", "프래그런스"]
ALCOHOL_EXACT = ["에탄올", "변성알코올", "알코올디내트", "알콜디내트",
                 "아이소프로필알코올", "t-부틸알코올"]

# 각질제거 산은 기존 정규화 모듈의 대표 성분명을 그대로 쓴다
EXFOLIANT_CANON = {"살리실릭애씨드", "락틱애씨드", "글라이콜릭애씨드"}

# (축 이름, 없을 때 붙일 문구, 있을 때 붙일 문구)
AXIS_LABEL = [
    ("sulfate",   "설페이트 무첨가",   "설페이트 계면활성제 있음"),
    ("fragrance", "향료 무첨가",       "향료 있음"),
    ("alcohol",   "에탄올 무첨가",     "에탄올 있음"),
    ("exfoliant", "각질제거 산 없음",  "각질제거 산 있음"),
]

MAX_SCORE = float(len(AXIS_LABEL))


def irritant_axes(ingredients) -> dict:
    """전성분 → 축마다 자극원이 들어 있는지. {'sulfate': True, ...}

    전성분 문자열을 한 번만 쪼갠다. find_ingredients 를 쓰면 안에서 또 쪼개므로
    쪼갠 토큰을 match_canonical 에 직접 넘긴다.
    """
    tokens = split_ingredients(ingredients)
    canon = match_canonical(tokens)

    return {
        "sulfate":   any(k in t for t in tokens for k in SULFATE_KEYS),
        "fragrance": any(t in FRAGRANCE_EXACT for t in tokens),
        "alcohol":   any(t in ALCOHOL_EXACT for t in tokens),
        "exfoliant": bool(canon & EXFOLIANT_CANON),
    }


def gentleness(ingredients):
    """
    전성분 → (점수, 없는 축 문구 목록, 있는 축 문구 목록)

    점수는 '없는 축의 개수' 다. 0.0 ~ 4.0.
    """
    has = irritant_axes(ingredients)
    absent, present = [], []
    for key, off_label, on_label in AXIS_LABEL:
        if has[key]:
            present.append(on_label)
        else:
            absent.append(off_label)
    return float(len(absent)), absent, present


def gentle_note(cand: dict) -> str:
    """사용자에게 보여줄 근거 문구. 코드가 데이터에서 만든다."""
    absent = cand.get("gentle_absent")
    if absent is None:
        _, absent, _ = gentleness(cand.get("ingredients", ""))
    return " · ".join(absent)


def gentle_reason(cand: dict) -> str:
    """
    증상이 모두 0단계일 때 쓰는 이유 문장. LLM 을 쓰지 않는다.

    증상이 없으면 설명할 증상도 없다. LLM 에게 맡기면 제품 설명을 베끼거나
    다른 후보의 이름을 끌어오는 일이 생겼다. 그래서 코드가 쓴다.
    문장은 그 상품에서 실제로 확인된 축으로만 만든다.
    """
    absent = cand.get("gentle_absent")
    if absent is None:
        _, absent, _ = gentleness(cand.get("ingredients", ""))

    head = "두피 상태가 전반적으로 양호합니다."
    if not absent:
        return f"{head} 특정 증상을 겨냥하기보다 현재 상태를 유지하는 쪽으로 골랐습니다."

    # 축 이름을 그대로 이어 붙이면 문장이 어색해진다. 조합별로 다르게 쓴다.
    named = [a.replace(" 무첨가", "").replace(" 없음", "") for a in absent]
    if len(named) == 1:
        joined = named[0]
    else:
        joined = (", ".join(named[:-1])
                  + _josa(named[-2], "과 ", "와 ") + named[-1])
    return (f"{head} {joined}{_josa(joined, '을', '를')} 넣지 않은 제품입니다. "
            f"평소 관리용으로 쓰기 좋습니다.")


def _josa(word: str, with_final: str, without_final: str) -> str:
    """단어의 받침을 보고 붙일 조사만 돌려준다. 단어는 포함하지 않는다.

    한글 음절에서 (코드 - 0xAC00) % 28 이 0이 아니면 종성이 있다.
    """
    w = word.strip()
    if not w:
        return with_final
    ch = w[-1]
    if "가" <= ch <= "힣":
        return with_final if (ord(ch) - 0xAC00) % 28 else without_final
    return with_final


if __name__ == "__main__":
    import csv

    cases = [
        ("정제수, 소듐라우레스설페이트, 향료, 살리실릭애씨드, 에탄올", "전부 있음"),
        ("정제수, 코코-글루코사이드, 글리세린", "전부 없음"),
        ("정제수, 페녹시에탄올, 세틸알코올, 글리세린", "오탐 확인용 — 전부 없어야 함"),
        ("정제수, 소듐C14-16올레핀설포네이트, 글리세린", "설페이트 아님"),
        ("정제수, 티이에이-라우릴설페이트, 글리세린", "설페이트 있음"),
    ]
    for ing, label in cases:
        sc, absent, present = gentleness(ing)
        print(f"{sc:.1f}  {label}")
        print(f"      없음: {absent}")
        print(f"      있음: {present}")
        print(f"      이유: {gentle_reason({'ingredients': ing})}")
        print()

    rows = [r for r in csv.DictReader(
        open("recommendation/data/products.csv", encoding="utf-8"))]
    sham = [r for r in rows if r.get("category") == "shampoo"]
    dist = {}
    for r in sham:
        sc, _, _ = gentleness(r.get("ingredients", ""))
        dist[sc] = dist.get(sc, 0) + 1
    print("샴푸 83개의 순한 정도 분포")
    for k in sorted(dist, reverse=True):
        print(f"  {k:.1f}점 {dist[k]:2d}개")
