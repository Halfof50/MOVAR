"""
성분 → 증상 적합도

역할이 바뀐 모듈이다.
이전 구조에서는 이 점수가 임베딩 유사도·별점과 가중합되어 최종 순위를 직접 결정했다.
새 구조에서는 가중합을 쓰지 않는다. RAG가 가져온 후보 상품에 대해
'이 상품이 어떤 증상에 대해 어떤 근거를 가지고 있는지'를 계산해
Local LLM 이 판단할 수 있는 구조화된 근거로 넘긴다.

점수 체계는 근거 수준에 따라 4단계.
    1.0  식약처 고시 조합 충족 / 사람 대상 비교 임상에서 기준 성분으로 쓰인 성분
    0.6  사람 대상 임상 1건 이상. 단 연구 농도나 적용 부위가 제품과 다름
    0.5  고시 조합의 일부만 포함 / 세포·체외 연구 수준
    0.3  주 효과가 아닌 보조 효과 / 두피가 아닌 부위 연구

같은 증상에 여러 성분이 걸리면  최댓값 + 0.1 × (성분 수 - 1).
최댓값만 쓰면 유효 성분 1개 제품과 4개 제품이 동점이 된다.
성분 수를 그대로 더하면 약한 성분을 모은 제품이 강한 성분 1개 제품을 넘어서므로
가산폭을 0.1로 제한한다.

성분표 위치는 가중치로 쓰지 않는다.
화장품법 시행규칙 별표4에 따라 1% 이하 성분은 순서에 상관없이 표시할 수 있어
표시 순서가 함량을 반영하지 않는다.
"""

from recommendation.config import SYMPTOMS
from recommendation.preprocessing.ingredient_normalizer import (
    find_ingredients, split_ingredients, match_canonical, ALIASES, EXCLUSIONS,
)

# 대표 성분 → ({증상: 점수}, 근거 키)
RULES = {
    # 비듬 — 비교 임상에서 기준 성분으로 쓰인 항진균 성분
    "징크피리치온":   ({"dandruff": 1.0, "hair_loss": 0.5},    ["S2", "S3", "S1"]),
    "피록톤올아민":   ({"dandruff": 1.0},                       ["S2", "S3"]),
    "클림바졸":       ({"dandruff": 1.0},                       ["S3"]),
    "티트리":         ({"dandruff": 0.6, "excess_sebum": 0.3},  ["S4"]),

    # 미세각질
    "살리실릭애씨드": ({"micro_keratin": 0.5, "dandruff": 0.3, "hair_loss": 0.5},
                       ["S5", "S9", "S1"]),
    "유레아":         ({"micro_keratin": 0.5},                  ["S12", "S13"]),
    "글라이콜릭애씨드": ({"micro_keratin": 0.3},                 ["S13", "S14"]),
    "락틱애씨드":     ({"micro_keratin": 0.3},                  ["S14", "S15"]),

    # 피지과다
    "나이아신아마이드": ({"excess_sebum": 0.5, "hair_loss": 0.5}, ["S6", "S1"]),

    # 진정 — 모낭사이홍반 / 모낭홍반농포
    "병풀":           ({"follicular_erythema": 0.5, "follicular_pustule": 0.5}, ["S7"]),
    "다이포타슘글리시리제이트": ({"follicular_erythema": 0.3, "follicular_pustule": 0.3},
                                ["S11"]),

    # 탈모
    "카페인":         ({"hair_loss": 0.5},                      ["S8"]),
    "덱스판테놀":     ({"hair_loss": 0.5, "follicular_erythema": 0.3}, ["S1", "S10"]),
    "비오틴":         ({"hair_loss": 0.5},                      ["S1"]),
    "멘톨":           ({"hair_loss": 0.5},                      ["S1"]),
}

# 식약처 탈모 증상 완화 기능성 고시 조합.
# 조합을 모두 포함하면 해당 증상 점수를 1.0 으로 올린다.
# 단순 대입이 아니라 max 로 올린다. 대입하면 성분 개수 가산분이 지워진다.
HAIR_LOSS_COMBOS = [
    {"덱스판테놀", "살리실릭애씨드", "멘톨"},
    {"나이아신아마이드", "덱스판테놀", "비오틴", "징크피리치온"},
]

COUNT_BONUS = 0.1

SOURCES = {
    "S1":  "식약처 기능성화장품 심사 규정 탈모 증상 완화 고시 성분 조합",
    "S2":  "Piroctone olamine+salicylic acid vs zinc pyrithione 비교 임상 (PubMed 18503415)",
    "S3":  "Piroctone olamine+climbazole vs zinc pyrithione 비교 임상 (PubMed 21272039)",
    "S4":  "5% tea tree oil shampoo 비듬 임상 (PubMed 12451368)",
    "S5":  "Salicylic acid 각질용해 작용 및 비듬 보조 역할",
    "S6":  "2% niacinamide 피지 분비 감소 임상 (PubMed 16766489)",
    "S7":  "Centella asiatica(마데카소사이드) 항염 작용 (PubMed 30452312, PMC11643272)",
    "S8":  "Caffeine 모낭 성장 촉진 체외 연구 (PubMed 17214716)",
    "S9":  "미국 OTC 비듬 기준: salicylic acid 1.8~3%, zinc pyrithione 0.3~2%",
    "S10": "덱스판테놀 SLS 자극 피부 홍반 감소 무작위 대조 연구 (PubMed 19753737)",
    "S11": "다이포타슘글리시리제이트 함유 보습제 아토피 피부염 임상 (PMC12302091)",
    "S12": "Urea 각질층 수분 결합 및 각질 분리 작용 (urea 제형 리뷰)",
    "S13": "Urea·salicylic acid·glycolic acid 조합 두피 각질 임상",
    "S14": "AHA(glycolic/lactic acid) 각질 탈락 촉진 작용",
    "S15": "Lactic acid 체외 각질세포 응집력 감소 연구",
}


def ingredient_scores(ingredients):
    """
    전성분 문자열 → (증상별 점수 dict, 증상별 근거 성분 dict)

    점수는 0 이상. 고시 조합과 성분 개수 가산이 겹치면 1.0 을 넘을 수 있다.
    새 구조에서는 이 값을 정규화하지 않고 그대로 LLM 에 넘긴다.
    순위 계산식에 들어가지 않으므로 상한을 맞출 필요가 없고,
    오히려 원래 값이 근거로서 읽기 쉽다.
    """
    found = find_ingredients(ingredients)

    scores   = {s: 0.0 for s in SYMPTOMS}
    evidence = {s: [] for s in SYMPTOMS}
    hits     = {s: [] for s in SYMPTOMS}

    for ing in sorted(found):
        rule, _ = RULES[ing]
        for sym, val in rule.items():
            hits[sym].append(val)
            evidence[sym].append(ing)

    for s in SYMPTOMS:
        if hits[s]:
            scores[s] = round(max(hits[s]) + COUNT_BONUS * (len(hits[s]) - 1), 2)

    for combo in HAIR_LOSS_COMBOS:
        if combo <= found:
            scores["hair_loss"] = max(scores["hair_loss"], 1.0)
            evidence["hair_loss"].append("식약처 고시 조합 충족")
            break

    return scores, evidence


def active_ingredients(ingredients) -> list:
    """점수 규칙에 걸린 유효 성분 목록. Document 생성과 LLM 근거 표시에 쓴다."""
    return sorted(find_ingredients(ingredients))


def source_list(evidence: dict) -> list:
    """근거 성분 dict → 출처 문자열 목록 (중복 제거)"""
    keys = []
    for ings in evidence.values():
        for ing in ings:
            for k in RULES.get(ing, ({}, []))[1]:
                if k not in keys:
                    keys.append(k)
    return [f"{k}: {SOURCES[k]}" for k in keys if k in SOURCES]


if __name__ == "__main__":
    import pandas as pd
    from recommendation.config import PRODUCTS_CSV, SYMPTOM_KR

    df = pd.read_csv(PRODUCTS_CSV, encoding="utf-8-sig")
    table = pd.DataFrame(list(df["ingredients"].apply(lambda x: ingredient_scores(x)[0])))

    print(f"상품 {len(df)}개\n")
    print("증상별 점수 > 0 인 상품 수")
    for s in SYMPTOMS:
        print(f"  {SYMPTOM_KR[s]:14s} {int((table[s] > 0).sum()):4d}"
              f"   최대 {table[s].max():.2f}   동점(최대값) {int((table[s] == table[s].max()).sum())}")
    print(f"\n성분 점수가 전부 0인 상품: {int((table.sum(axis=1) == 0).sum())}")
