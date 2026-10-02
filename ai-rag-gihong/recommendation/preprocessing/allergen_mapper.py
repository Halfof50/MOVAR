"""
알레르기 관련 파생 정보

성격이 다른 두 가지를 분리해서 다룬다.

 1. 접촉 알레르겐 (contact)
    식약처가 고시한 착향제 알레르기 유발성분 25종.
    씻어내는 제품 0.01% 초과, 씻어내지 않는 제품 0.001% 초과 시 전성분에 표시해야 한다.
    표시 의무가 있어 전성분에 적혀 있으면 실제로 들어 있다고 볼 수 있다.
    화장품을 피부에 바르는 상황에 대한 자료라 근거가 직접적이다.

 2. 음식 알레르기 관련 성분 (food)
    사용자가 등록한 음식 알레르기와 '유래 원료가 같은' 화장품 성분을 찾는다.
    여기서 판단하는 것은 원료의 동일성뿐이다.
    음식 섭취 반응과 피부 도포 반응은 같지 않으므로
    이 모듈은 반응 여부나 사용 금지를 판단하지 않는다.
    출력 문구도 '관련 가능성이 있는 성분이 확인됨' 수준으로 고정한다.

매칭은 성분명 전체를 등록해서 한다. 짧은 조각으로 부분 문자열 검색을 하면 깨진다.
데이터셋에서 확인된 사례.
    '위트'(밀)   → 스위트아몬드오일        6건
    '밀'         → 약모밀추출물           20건
    '락토'(우유) → 락토바실러스발효물      14건 (유산균이며 우유 아님)
    '굴'(조개)   → 인동덩굴꽃추출물         2건
    '잣'         → 솔잣나무오일 (솔잎 유래)
    '피넛'(땅콩) → 잉카피넛씨오일 (사차인치)
그래서 각 항목마다 deny 목록을 함께 둔다.
"""

from recommendation.preprocessing.ingredient_normalizer import split_ingredients

# ──────────────────────────────────────────────────────────
# 1. 착향제 알레르기 유발성분 25종 (식약처 고시, 2020-01-01 시행)
# ──────────────────────────────────────────────────────────
CONTACT_ALLERGENS = [
    "아밀신남알", "벤질알코올", "신나밀알코올", "시트랄", "유제놀",
    "하이드록시시트로넬알", "아이소유제놀", "아밀신나밀알코올", "벤질살리실레이트",
    "신남알", "쿠마린", "제라니올", "아니스알코올", "벤질신나메이트", "파네솔",
    "부틸페닐메틸프로피오날", "리날룰", "벤질벤조에이트", "시트로넬올", "헥실신남알",
    "리모넨", "메틸2-옥티노에이트", "알파-아이소메틸아이오논",
    "참나무이끼추출물", "나무이끼추출물",
]

# 긴 이름이 짧은 이름을 포함하는 경우 긴 쪽을 먼저 본다.
# '신남알'은 '아밀신남알', '헥실신남알'의 부분 문자열이다.
_CONTACT_ORDER = sorted(CONTACT_ALLERGENS, key=len, reverse=True)

# ──────────────────────────────────────────────────────────
# 2. 음식 알레르겐 → 같은 원료에서 나온 화장품 성분
#
#    level
#      direct    : 해당 원료의 오일·추출물·단백질. 단백질이 남아 있을 수 있는 형태
#      processed : 화학 처리를 거친 계면활성제·에스터 등. 단백질 잔류 가능성이 낮음
# ──────────────────────────────────────────────────────────
FOOD_ALLERGEN_RULES = {
    "알류": {
        "label": "알류(가금류)",
        "direct": ["에그", "에그오일", "에그추출물", "하이드롤라이즈드에그",
                   "알부민", "오보트랜스페린", "라이소자임"],
        "processed": [],
        "deny": [],
    },
    "우유": {
        "label": "우유",
        "direct": ["밀크프로틴", "밀크단백질", "하이드롤라이즈드밀크", "카세인",
                   "소듐카세인에이트", "락토페린", "웨이프로틴", "유청단백질",
                   "락토스", "버터밀크"],
        "processed": [],
        # 락토바실러스·락토코쿠스는 유산균이고 우유가 아니다.
        # 소이밀크·코코넛밀크·아몬드밀크는 식물성이다.
        "deny": ["락토바실러스", "락토코쿠스", "소이밀크", "코코넛밀크",
                 "아몬드밀크", "라이스밀크", "오트밀크"],
    },
    "메밀": {
        "label": "메밀",
        "direct": ["메밀추출물", "메밀씨", "버크위트", "패고파이럼"],
        "processed": [],
        "deny": ["약모밀"],          # 약모밀 = 어성초. 메밀과 다른 식물
    },
    "땅콩": {
        "label": "땅콩",
        "direct": ["피넛오일", "땅콩오일", "땅콩추출물", "아라키스하이포게아"],
        "processed": [],
        "deny": ["잉카피넛"],        # 사차인치. 땅콩이 아니다
    },
    "대두": {
        "label": "대두",
        "direct": ["소이빈", "소이단백질", "하이드롤라이즈드소이", "소이아미노산",
                   "글라이신소자", "대두추출물", "콩추출물", "콩발효", "소이밀크"],
        "processed": ["소이아미도프로필", "소이에칠", "하이드로제네이티드소이빈"],
        "deny": [],
    },
    "밀": {
        "label": "밀",
        "direct": ["위트저머", "위트브란", "밀단백질", "하이드롤라이즈드밀",
                   "밀싹추출물", "밀배아", "트리티컴벌가레", "글루텐",
                   "위트아미노애씨드", "위트프로틴"],
        "processed": [],
        # '위트'만 보면 스위트아몬드가 걸린다. 위 목록은 모두 '위트+단어' 형태
        "deny": ["스위트", "로우스위트"],
    },
    "호두": {
        "label": "호두",
        "direct": ["호두", "월넛", "쥬글란스"],
        "processed": [],
        "deny": [],
    },
    "잣": {
        "label": "잣",
        "direct": ["잣씨오일", "잣추출물", "파인너트", "피누스코라이엔시스"],
        "processed": [],
        "deny": ["솔잣나무", "잣나무캘러스"],   # 솔잎·캘러스 유래로 잣(종실)이 아니다
    },
    "복숭아": {
        "label": "복숭아",
        "direct": ["복숭아", "프루누스페르시카"],
        "processed": [],
        "deny": [],
    },
    "토마토": {
        "label": "토마토",
        "direct": ["토마토", "라이코퍼시컴"],
        "processed": [],
        "deny": [],
    },
    "갑각류": {
        "label": "게·새우(갑각류)",
        "direct": ["키토산", "키틴", "하이드롤라이즈드키틴", "글루코사민"],
        "processed": ["카복시메틸키토산"],
        "deny": [],
    },
    "조개류": {
        "label": "조개류(굴·전복·홍합)",
        "direct": ["진주추출물", "하이드롤라이즈드진주", "진주가루",
                   "굴추출물", "전복추출물", "홍합추출물"],
        "processed": [],
        "deny": ["덩굴"],            # 인동덩굴·으름덩굴은 식물이다
    },
    "아황산류": {
        "label": "아황산류",
        "direct": ["소듐설파이트", "소듐바이설파이트", "소듐메타바이설파이트",
                   "포타슘메타바이설파이트", "암모늄설파이트"],
        "processed": [],
        "deny": [],
    },
    # 국내 표시 대상은 아니지만 문의가 많은 항목
    "참깨": {
        "label": "참깨",
        "direct": ["참깨", "세사미", "세사뭄인디쿰"],
        "processed": [],
        "deny": [],
    },
    "코코넛": {
        "label": "코코넛",
        "direct": ["코코넛야자", "코코넛오일", "코코넛애씨드", "코코스뉴시페라",
                   "코코넛추출물"],
        # 코코-글루코사이드, 소듐코코일이세티오네이트 등은 코코넛 유래 계면활성제다.
        # 데이터셋 146개 중 160건이 걸려 거의 모든 제품에 해당한다.
        # 그대로 경고로 올리면 의미가 없어 processed 로 분리한다.
        "processed": ["코코-", "코코일", "코카미도", "코코암포", "코코베타인",
                      "코코-베타인", "코코글루코사이드"],
        "deny": [],
    },
}

# 표시 대상이지만 화장품 성분으로 신뢰할 매핑을 만들지 못한 항목.
# 임의로 추정하지 않고 비워 둔다.
FOOD_ALLERGEN_NO_MAPPING = {
    "고등어": "어종을 특정할 수 있는 성분명이 전성분에 나타나지 않음",
    "오징어": "같음",
    "돼지고기": "콜라겐·엘라스틴·플라센타는 동물 종을 표기하지 않는 경우가 많음",
    "소고기": "같음",
    "닭고기": "같음",
}

FOOD_ALLERGEN_KEYS = list(FOOD_ALLERGEN_RULES.keys())


def contact_allergens(ingredients) -> list:
    """전성분 → 포함된 착향제 알레르기 유발성분 목록"""
    text = "|".join(split_ingredients(ingredients))
    found = []
    # 긴 이름부터 찾고, 찾은 구간은 텍스트에서 지운다.
    # '신남알'은 '아밀신남알'·'헥실신남알'의 부분 문자열이므로
    # 긴 쪽을 먼저 제거해야 단독 표기된 신남알만 남는다.
    for name in _CONTACT_ORDER:
        if name in text:
            found.append(name)
            text = text.replace(name, "|")
    return sorted(found, key=CONTACT_ALLERGENS.index)


def food_allergen_matches(ingredients, allergen_keys=None) -> list:
    """
    전성분 → 음식 알레르겐과 유래 원료가 같은 성분 목록

    allergen_keys 를 주면 그 항목만 검사한다. 없으면 전체를 검사한다.
    반환 예:
      [{"allergen": "알류", "label": "알류(가금류)", "level": "direct",
        "matched": ["하이드롤라이즈드에그프로틴"],
        "basis": "유래 원료가 같은 성분"}]
    """
    tokens = split_ingredients(ingredients)
    keys = allergen_keys if allergen_keys is not None else FOOD_ALLERGEN_KEYS

    out = []
    for key in keys:
        rule = FOOD_ALLERGEN_RULES.get(key)
        if not rule:
            continue
        for level in ("direct", "processed"):
            hits = []
            for t in tokens:
                if any(d in t for d in rule["deny"]):
                    continue
                if any(n in t for n in rule[level]):
                    hits.append(t)
            if hits:
                out.append({
                    "allergen": key,
                    "label": rule["label"],
                    "level": level,
                    "matched": sorted(set(hits)),
                    "basis": ("유래 원료가 같은 성분"
                              if level == "direct"
                              else "같은 원료에서 화학 처리를 거쳐 만든 성분"),
                })
    return out


def allergen_info(ingredients) -> dict:
    """인덱스에 저장할 알레르기 파생 정보.

    음식 알레르겐은 사용자가 등록한 항목을 모르는 적재 시점이므로 전체를 계산해 둔다.
    조회 시점에 사용자 등록 항목으로 걸러 쓴다.
    """
    matches = food_allergen_matches(ingredients)
    return {
        "contact_allergens": contact_allergens(ingredients),
        "food_allergen_tags": sorted({m["allergen"] for m in matches}),
        "food_allergen_matches": matches,
    }


def caution_sentence(matches: list) -> str:
    """사용자에게 보여줄 주의 문구. 단정하지 않는다."""
    if not matches:
        return ""
    direct = [m for m in matches if m["level"] == "direct"]
    use = direct or matches
    labels = ", ".join(sorted({m["label"] for m in use}))
    names = ", ".join(sorted({n for m in use for n in m["matched"]})[:4])
    return (f"등록한 알레르기 정보({labels})와 유래 원료가 같은 성분({names})이 확인되었습니다. "
            f"사용 전 전성분을 확인하시기 바랍니다.")


if __name__ == "__main__":
    import pandas as pd
    from collections import Counter
    from recommendation.config import PRODUCTS_CSV

    df = pd.read_csv(PRODUCTS_CSV, encoding="utf-8-sig")

    print("=== 착향제 알레르기 유발성분 ===")
    cnt, per = Counter(), []
    for s in df["ingredients"]:
        f = contact_allergens(s)
        per.append(len(f))
        cnt.update(f)
    print(f"1종 이상 포함: {sum(1 for x in per if x)}개 / {len(df)}개"
          f"  평균 {sum(per)/len(per):.1f}종  최대 {max(per)}종")
    for k, v in cnt.most_common():
        print(f"  {k:22s} {v}")

    print("\n=== 음식 알레르겐 관련 성분 ===")
    tag = Counter()
    detail = {}
    for s in df["ingredients"]:
        for m in food_allergen_matches(s):
            tag[(m["allergen"], m["level"])] += 1
            detail.setdefault((m["allergen"], m["level"]), set()).update(m["matched"])
    for (k, lv), v in sorted(tag.items(), key=lambda x: -x[1]):
        print(f"  {k:8s} {lv:9s} {v:4d}개  예: {', '.join(sorted(detail[(k,lv)])[:4])}")

    print("\n매핑을 만들지 않은 표시 대상")
    for k, why in FOOD_ALLERGEN_NO_MAPPING.items():
        print(f"  {k}: {why}")
