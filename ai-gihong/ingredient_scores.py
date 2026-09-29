"""
성분 → 증상 점수표
- 성분과 증상의 연결은 아래 SOURCES의 근거 자료를 기준으로 함
- 점수 크기는 근거 수준에 따라 3단계로 부여
    1.0 : 식약처 고시 조합 충족 / 사람 대상 비교 임상에서 기준 성분으로 쓰인 성분
    0.6 : 사람 대상 임상 1건 이상 (단, 농도·부위가 제품과 다름)
    0.5 : 식약처 고시 조합의 일부만 포함 / 세포·체외 연구 수준
    0.3 : 주 효과가 아닌 보조 효과 / 두피가 아닌 부위 연구
- 성분표 위치 가중치는 사용하지 않음
  (화장품법 시행규칙 별표4: 1% 이하 성분은 순서에 상관없이 표시 가능 → 위치가 함량을 반영하지 않음)
"""

SYMPTOMS = ["micro_keratin", "excess_sebum", "follicular_erythema",
            "follicular_pustule", "dandruff", "hair_loss"]

# 성분 표기 변형 → 대표 이름
ALIASES = {
    "덱스판테놀": ["덱스판테놀"],
    "살리실릭애씨드": ["살리실릭애씨드", "소듐살리실레이트", "살리실산"],
    "멘톨": ["엘-멘톨", "L-멘톨", "멘톨"],
    "나이아신아마이드": ["나이아신아마이드"],
    "비오틴": ["비오틴", "바이오틴"],
    "징크피리치온": ["징크피리치온"],
    "피록톤올아민": ["피록톤올아민"],
    "클림바졸": ["클림바졸"],
    "티트리": ["티트리잎오일", "티트리잎추출물", "티트리오일", "티트리"],
    "카페인": ["카페인"],
    "병풀": ["마데카소사이드", "아시아티코사이드", "병풀추출물", "병풀잎추출물",
             "병풀꽃/잎/줄기추출물", "센텔라아시아티카"],
    "다이포타슘글리시리제이트": ["다이포타슘글리시리제이트", "다이포타슘글리시리제이트액",
                          "글리시리제이트", "글리시리진"],
    "유레아": ["유레아", "우레아"],
    "글라이콜릭애씨드": ["글라이콜릭애씨드"],
    "락틱애씨드": ["락틱애씨드", "소듐락테이트"],
}

# 이름은 비슷하지만 작용이 다른 성분 → 매칭 전에 제거
# 하이드록시에틸우레아는 보습제이며 각질용해 작용이 없음
EXCLUDE = ["하이드록시에틸우레아", "하이드록시에틸유레아"]

# 대표 성분 → {증상: 점수}, 근거 키
RULES = {
    # 비듬: 비교 임상에서 기준 성분으로 쓰인 항진균 성분
    "징크피리치온":   ({"dandruff": 1.0, "hair_loss": 0.5}, ["S2", "S3", "S1"]),
    "피록톤올아민":   ({"dandruff": 1.0},                   ["S2", "S3"]),
    "클림바졸":       ({"dandruff": 1.0},                   ["S3"]),
    "티트리":         ({"dandruff": 0.6, "excess_sebum": 0.3}, ["S4"]),

    # 각질: 각질용해 성분. 비듬엔 보조
    # 살리실릭애씨드는 146개 중 94개에 들어 있어 존재만으로 1.0을 주면 변별력이 없음.
    # 탈모 고시 조합의 농도는 0.25%로, 미국 OTC 비듬 기준(1.8~3%)보다 훨씬 낮음(S9)
    # → 각질 0.5로 제한. 스케일러 제품의 각질 가산은 카테고리 단계에서 따로 처리
    "살리실릭애씨드": ({"micro_keratin": 0.5, "dandruff": 0.3, "hair_loss": 0.5},
                       ["S5", "S9", "S1"]),
    # 유레아는 두피 부위 근거가 있어 0.5, 나머지 둘은 두피 밖 부위 연구라 0.3
    "유레아":           ({"micro_keratin": 0.5}, ["S12", "S13"]),
    "글라이콜릭애씨드": ({"micro_keratin": 0.3}, ["S13", "S14"]),
    "락틱애씨드":       ({"micro_keratin": 0.3}, ["S14", "S15"]),

    # 피지
    "나이아신아마이드": ({"excess_sebum": 0.5, "hair_loss": 0.5}, ["S6", "S1"]),

    # 진정 (모낭사이홍반·모낭홍반농포)
    "병풀":           ({"follicular_erythema": 0.5, "follicular_pustule": 0.5}, ["S7"]),

    # 탈모
    "카페인":         ({"hair_loss": 0.5},                  ["S8"]),
    "덱스판테놀": ({"hair_loss": 0.5, "follicular_erythema": 0.3}, ["S1", "S10"]),
    "다이포타슘글리시리제이트": ({"follicular_erythema": 0.3, "follicular_pustule": 0.3}, ["S11"]),
    "비오틴":         ({"hair_loss": 0.5},                  ["S1"]),
    "멘톨":           ({"hair_loss": 0.5},                  ["S1"]),
}

# 식약처 탈모 증상 완화 고시 조합 (둘 중 하나를 모두 포함하면 hair_loss = 1.0)
HAIR_LOSS_COMBOS = [
    {"덱스판테놀", "살리실릭애씨드", "멘톨"},
    {"나이아신아마이드", "덱스판테놀", "비오틴", "징크피리치온"},
]

SOURCES = {
    "S1": "식약처 기능성화장품 심사 규정 탈모 증상 완화 고시 성분 조합",
    "S2": "Piroctone olamine+salicylic acid vs zinc pyrithione 비교 임상 (PubMed 18503415)",
    "S3": "Piroctone olamine+climbazole vs zinc pyrithione 비교 임상 (PubMed 21272039)",
    "S4": "5% tea tree oil shampoo 비듬 임상 (PubMed 12451368)",
    "S5": "Salicylic acid 각질용해 작용 및 비듬 보조 역할",
    "S6": "2% niacinamide 피지 분비 감소 임상 (PubMed 16766489)",
    "S7": "Centella asiatica(마데카소사이드) 항염 작용 (PubMed 30452312, PMC11643272)",
    "S8": "Caffeine 모낭 성장 촉진 체외 연구 (PubMed 17214716)",
    "S9": "미국 OTC 비듬 기준: salicylic acid 1.8~3%, zinc pyrithione 0.3~2%",
    "S10": "덱스판테놀 SLS 자극 피부 홍반 감소 무작위 대조 연구 (PubMed 19753737)",
    "S11": "다이포타슘글리시리제이트 함유 보습제 아토피 피부염 임상 (PMC12302091)",
    "S12": "고농도 유레아 각질용해·두피 각질 연화 임상 근거 리뷰 (Int J Clin Pract 2020, doi 10.1111/ijcp.13740)",
    "S13": "유레아+글라이콜릭애씨드+살리실릭애씨드 샴푸 두피 각질·홍반 개방 임상 n=10 (Cogent Medicine 2018, doi 10.1080/2331205X.2018.1475095)",
    "S14": "AHA 각질박리 작용 사람 피부 연구 (PubMed 16469079)",
    "S15": "락틱애씨드 각질층 지질·배리어 체외 연구 (PubMed 8818186)",
}


def find_ingredients(ingredients: str) -> set:
    text = str(ingredients)
    for w in EXCLUDE:          
        text = text.replace(w, "")
    found = set()
    for key, names in ALIASES.items():
        if any(n in text for n in names):
            found.add(key)
    return found


def ingredient_scores(ingredients: str):
    """
    반환: (6개 증상 점수 dict, 근거로 쓰인 성분 dict)
    같은 증상에 여러 성분이 걸리면 최댓값 사용 (성분 개수로 점수가 부풀지 않게)
    """
    found = find_ingredients(ingredients)
    scores = {s: 0.0 for s in SYMPTOMS}
    evidence = {s: [] for s in SYMPTOMS}

    hits = {s: [] for s in SYMPTOMS}
    for ing in found:
        rule, _ = RULES[ing]
        for sym, val in rule.items():
            hits[sym].append(val)
            evidence[sym].append(ing)

    for sym, vals in hits.items():
        if vals:
            scores[sym] = max(vals) + 0.1 * (len(vals) - 1)

    for combo in HAIR_LOSS_COMBOS:
        if combo <= found:
            scores["hair_loss"] = max(scores["hair_loss"], 1.0)
            evidence["hair_loss"].append("식약처 고시 조합 충족")
            break

    return scores, evidence


if __name__ == "__main__":
    import pandas as pd
    df = pd.read_csv("data/products.csv", encoding="utf-8-sig")
    rows = df["ingredients"].apply(lambda x: ingredient_scores(x)[0])
    table = pd.DataFrame(list(rows))
    print("[증상별 점수 > 0 인 상품 수]")
    print((table > 0).sum())
    print("\n[증상별 점수 1.0 이상상인 상품 수]")
    print((table >= 1.0).sum())
    print("\n성분 점수가 전부 0인 상품:", int((table.sum(axis=1) == 0).sum()))
    print("\n[증상별 최댓값 / 동점 상품 수]")
    for s in SYMPTOMS:
        mx = table[s].max()
        print(f"{s:20s} {mx:.2f}  동점 {(table[s] == mx).sum()}개")