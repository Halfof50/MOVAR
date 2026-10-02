"""
Local LLM 프롬프트 생성

LLM 이 하는 일은 두 가지로 제한한다.
    후보 안에서 고르기
    왜 그 사용자에게 맞는지 설명하기

LLM 이 하지 않는 일.
    성분 이름을 적는 것      → 근거 성분은 코드가 데이터에서 붙인다
    가격·평점·리뷰 수를 적는 것 → 코드가 화면에 숫자로 찍는다
    상품명을 적는 것          → 코드가 DB 값으로 찍는다
    알레르기 판정            → 별도 모듈에서 처리할 예정. 지금은 아예 다루지 않는다

성분 이름을 LLM 에게 맡기지 않는 이유.
    측정 결과 이유 문장 13건 중 11건이 틀렸다.
      2건  그 상품에 아예 없는 성분을 적음  (예: 없는 제품에 '징크피리치온')
      9건  다른 증상의 성분을 그 증상 근거로 적음 (예: '탈모에 쓰이는 클림바졸')
    규칙으로 금지해도 지켜지지 않았다. 쓸 일 자체를 없애는 쪽이 확실하다.

리뷰 수와 가격도 같은 이유로 맡기지 않는다.
    '리뷰 수가 많은 편이라' 라고 쓴 32건 중 7건이 리뷰 10~230건인 상품이었다.
    한 호출에 리뷰 26,100건짜리가 섞여 있으면 그 숫자가 10건짜리 상품에도 붙었다.
    고른 뒤에 그 후보의 칸을 다시 보지 않기 때문이다.

상품명을 쓰라는 규칙은 지웠다.
    출력 형식에 product_name 칸이 없는데 '이름을 그대로 쓴다' 는 규칙이 있었다.
    넣을 칸이 없으니 모델이 reason 에 넣었고, 그 이름이 다른 후보 것이었다.
    이름은 output_parser 가 DB 값으로 덮어쓰므로 이 규칙은 보호하는 것이 없었다.

전체 전성분은 넣지 않는다 (include_full_ingredients=False).
후보 12개의 전성분을 그대로 넣으면 1만 2천자 규모가 되어
로컬 8B 모델에서는 지시 준수율이 떨어지고 응답이 느려진다.
"""

import random

from recommendation.config import (
    CATEGORY_KR, LEVEL_KR, PICK_PER_CATEGORY, SHUFFLE_CANDIDATES,
    SYMPTOMS, SYMPTOM_KR,
)

PROFILE_LABEL = {
    "age_group":      "연령대",
    "wash_frequency": "머리 감는 주기",
    "max_price":      "희망 가격 상한",
}

COMBO_MARK = "식약처 고시 조합 충족"


def format_symptoms(levels: dict) -> str:
    """레벨 1 이상만 보여준다.

    0단계까지 전부 나열하면 '쓰지 말라'고 규칙에 적어둬도 계속 언급한다.
    0단계 증상은 규칙의 금지 목록에만 적는다.
    """
    on = [s for s in SYMPTOMS if levels.get(s, 0) > 0]
    if not on:
        return "- 6개 증상이 모두 0단계입니다."
    return "\n".join(
        f"- {SYMPTOM_KR[s]}: {levels[s]}단계 {LEVEL_KR[levels[s]]}" for s in on
    )


def format_profile(profile: dict) -> str:
    if not profile:
        return "- 등록된 정보 없음"
    lines = []
    for key, label in PROFILE_LABEL.items():
        v = profile.get(key)
        if v in (None, "", [], {}):
            continue
        if key == "max_price":
            v = f"{int(v):,}원"
        lines.append(f"- {label}: {v}")
    return "\n".join(lines) or "- 등록된 정보 없음"


def format_candidate(c: dict, levels: dict, include_full_ingredients=False) -> str:
    """후보 한 건.

    성분 적합도는 사용자가 실제로 가진 증상에 대해서만 보여준다.
    0단계 증상의 점수까지 보여주면 그걸 근거로 문장을 쓴다.
    """
    lines = [
        f"product_id: {c['product_id']}",
        f"상품명: {c.get('name_clean') or c.get('name')}",
        f"브랜드: {c.get('brand') or '미상'}",
        f"제품 유형: {CATEGORY_KR.get(c.get('category'), c.get('category'))}",
    ]
    spec = str(c.get("spec") or "").strip()
    if len(spec) >= 20:
        lines.append(f"제품 설명: {spec}")

    price = c.get("price")
    rating = c.get("rating")
    lines.append(f"가격: {price:,}원" if price else "가격: 미상")
    lines.append(
        f"평점: {rating} / 리뷰 {c.get('reviews', 0):,}건" if rating
        else f"평점: 미상 / 리뷰 {c.get('reviews', 0):,}건"
    )

    sc = c.get("symptom_scores", {}) or {}
    ev = c.get("score_evidence", {}) or {}
    on = [s for s in SYMPTOMS if levels.get(s, 0) > 0]
    if on:
        lines.append("성분 적합도 (괄호 안이 그 증상의 근거 성분)")
        for s in on:
            v = sc.get(s, 0)
            src = ", ".join(ev.get(s) or []) if v > 0 else ""
            lines.append(f"  {SYMPTOM_KR[s]} {v:.1f}"
                         + (f" ({src})" if src else " (근거 성분 없음)"))

    lines.append(f"검색 유사도: {c.get('similarity', 0):.3f}")

    if include_full_ingredients:
        lines.append(f"전체 전성분: {c.get('ingredients', '')}")

    return "\n".join(lines)


def build_rules(pick: int, symptom_rule: str) -> str:
    """상황에 해당하는 규칙만 모아 번호를 매긴다.

    규칙이 많을수록 지시 준수율이 떨어진다.
    17개까지 늘렸을 때는 문장이 깨지고 주 증상을 잘못 고르는 현상이 나타났다.
    해당 없는 규칙은 아예 넣지 않는다.
    """
    rules = [
        "아래 후보 목록에 있는 product_id 만 추천한다. 목록에 없는 상품을 만들지 않는다.",
        symptom_rule,
        "다음은 이유에 쓰지 않는다. 모두 화면에 따로 표시되므로 적을 필요가 없다.\n"
        "성분 이름, 성분 적합도 숫자, 가격, 평점, 리뷰 수, 상품명.",
        "제공되지 않은 효능을 주장하지 않는다. 혈액순환, 피로 회복 같은 표현을 쓰지 않는다.",
        "한국어 존댓말로 쓴다. 이유는 1~2문장.",
        "같은 브랜드를 2개 이상 고르지 않는다.",
        f"정확히 {pick}개를 고른다. 더도 덜도 안 된다.",
        "JSON 만 출력한다. 설명 문장이나 코드 블록 표시를 붙이지 않는다.",
    ]
    body = "\n".join(f"{i}. {r}" for i, r in enumerate(rules, start=1))
    return "[지켜야 할 규칙]\n" + body


# 예시에 실제 증상명과 성분명을 쓰면 모델이 그 문장을 통째로 베낀다.
# 0단계인 증상을 '2단계로 가장 두드러지는데' 라고 쓴 출력이 실제로 나왔다.
# 예시에 실제 증상명과 성분명을 쓰면 모델이 그 문장을 통째로 베낀다.
# 0단계인 증상을 '2단계로 가장 두드러지는데' 라고 쓴 출력이 실제로 나왔다.
#
# 증상이 하나뿐인데 '함께 나타난 증상' 문장을 쓴 경우가 나왔다.
# 규칙으로 금지해도 쓸 문장이 눈앞에 있으면 쓴다.
# 그래서 해당되는 쪽만 프롬프트에 넣는다. format_symptoms, build_rules 와 같은 방식이다.

_EXAMPLE_HEAD = """[이유 작성 예시]
형식만 보이기 위한 것이다. 문장을 그대로 베끼지 않는다.
한 번에 고르는 제품들의 이유는 서로 다른 문장이어야 한다.
"""

_EXAMPLE_SINGLE = """
1순위에만 쓸 수 있는 표현
  "후보 중 해당 증상에 대한 성분 근거가 가장 넓은 제품입니다."

2·3순위에 쓸 수 있는 표현
  "해당 증상 하나에 초점이 맞춰진 구성입니다."
  "그 증상에 필요한 구성을 갖추고 있습니다."
  "증상 하나만 다루면 되는 상황에 맞는 구성입니다."
"""

_EXAMPLE_MULTI = """
1순위에만 쓸 수 있는 표현 — '가장' 은 한 제품에만 붙인다
  "가장 심한 증상에 대해 후보 중 성분 근거가 가장 넓은 제품입니다."
  "여러 증상을 한 제품으로 같이 관리할 수 있습니다."

2·3순위에 쓸 수 있는 표현
  "주요 증상에 필요한 구성을 갖추면서 함께 나타난 증상도 다룹니다."
  "두 증상 중 어느 한쪽에 치우치지 않게 구성되어 있습니다."
  "주요 증상에 집중된 구성이라 그 증상을 먼저 잡고 싶을 때 맞습니다."
  "증상이 여러 개일 때 덮는 범위가 넓은 편입니다."
"""

_EXAMPLE_BAD = """
나쁜 예와 그 이유
  "살리실릭애씨드가 들어 있습니다"              → 성분 이름을 적었다
  "덱스판테놀, 병풀도 함께 쓸 수 있는 구성입니다"   → 성분 이름을 나열했다
  "비듬 1.1, 탈모 0.0"                      → 숫자를 그대로 옮겨 적었다
  "리뷰 수가 많은 편입니다"                    → 리뷰 수는 화면에 따로 나온다
  "가격이 저렴합니다"                         → 가격도 화면에 따로 나온다
  상품명을 이유에 적는 것                      → 상품명을 적었다. 화면에 따로 나온다
  "탈모 개선에 도움이 됩니다"                  → 0단계인 증상을 근거로 들었다
  "혈액순환을 도와줍니다"                      → 제공되지 않은 효능을 지어냈다
  "두피에 좋다."                             → 존댓말이 아니다"""


def build_reason_example(active_count: int) -> str:
    """증상 개수에 해당하는 예시만 넣는다.

    둘 다 넣으면 증상이 하나인데 '함께 나타난 증상' 문장을 쓴다.
    """
    body = _EXAMPLE_SINGLE if active_count <= 1 else _EXAMPLE_MULTI
    return _EXAMPLE_HEAD + body + _EXAMPLE_BAD

CATEGORY_OUTPUT_FORMAT = """[출력 형식]
{
  "recommendations": [
    {
      "rank": 1,
      "product_id": 0,
      "reason": "이 상품을 추천하는 이유 1~2문장",
      "matched_symptoms": ["hair_loss"]
    }
  ]
}"""


def build_category_prompt(symptoms: dict, profile: dict, candidates: list,
                          category: str, pick: int = PICK_PER_CATEGORY,
                          include_full_ingredients: bool = False,
                          shuffle: bool = None,
                          seed: int = 0) -> str:
    """후보가 모두 같은 카테고리인 프롬프트. 정확히 pick 개를 고르게 한다."""
    items = list(candidates)
    if SHUFFLE_CANDIDATES if shuffle is None else shuffle:
        random.Random(seed).shuffle(items)

    kr = CATEGORY_KR.get(category, category)
    blocks = "\n\n".join(
        f"[후보 {i}]\n" + format_candidate(c, symptoms, include_full_ingredients)
        for i, c in enumerate(items, start=1)
    )
    ids = ", ".join(str(c["product_id"]) for c in items)

    # '레벨 0인 증상' 이라고만 적으면 지켜지지 않는다. 증상 이름을 직접 나열한다.
    active = [SYMPTOM_KR[s] for s in SYMPTOMS if symptoms.get(s, 0) > 0]
    zero = [SYMPTOM_KR[s] for s in SYMPTOMS if symptoms.get(s, 0) == 0]
    if active:
        symptom_rule = (f"이유에 쓸 수 있는 증상은 이것뿐이다: {', '.join(active)}\n"
                        f"   다음 증상은 0단계다. 이유에 쓰지 않는다: {', '.join(zero)}"
                        if zero else
                        f"이유에 쓸 수 있는 증상은 이것뿐이다: {', '.join(active)}")
    else:
        # 증상이 모두 0단계인 경우 service 는 이 프롬프트를 쓰지 않는다.
        # pick_gentle 이 순한 정도로 고르고 이유도 코드가 쓴다.
        # 이 분기는 프롬프트를 직접 만들어 볼 때만 쓰인다.
        symptom_rule = ("증상이 모두 0단계다. 특정 증상을 근거로 들지 않는다. "
                        "후보 중 무엇을 골랐는지만 간단히 쓴다.")

    return f"""너는 두피 상태와 사용자 정보를 보고 주어진 {kr} 후보 중에서 {pick}개를 고르는 역할이다.
후보는 모두 {kr} 이다. 다른 유형의 제품은 고려하지 않는다.

[두피 분석 결과]
{format_symptoms(symptoms)}

[사용자 정보]
{format_profile(profile)}

[{kr} 후보 {len(items)}개]
{blocks}

사용 가능한 product_id: {ids}

{build_rules(pick, symptom_rule)}

{build_reason_example(len(active))}

{CATEGORY_OUTPUT_FORMAT}
"""


def evidence_note(cand: dict, levels: dict) -> str:
    """사용자에게 보여줄 근거 성분 문구. 코드가 데이터에서 만든다.

    LLM 이 쓴 성분 이름은 쓰지 않는다. 틀려도 화면에 나가지 않게 하기 위해서다.
    '식약처 고시 조합 충족' 은 성분이 아니므로 따로 떼어 적는다.
    여기 적히는 것은 점수표에 등록된 성분 중 그 제품에서 검출된 것뿐이다.
    """
    sc = cand.get("symptom_scores", {}) or {}
    ev = cand.get("score_evidence", {}) or {}
    parts = []
    for s in sorted(SYMPTOMS, key=lambda x: -levels.get(x, 0)):
        if levels.get(s, 0) <= 0 or sc.get(s, 0) <= 0:
            continue
        ings = [x for x in (ev.get(s) or []) if x != COMBO_MARK]
        txt = ", ".join(ings)
        if COMBO_MARK in (ev.get(s) or []):
            txt = (txt + " / " if txt else "") + "식약처 탈모 고시 조합 충족"
        if txt:
            parts.append(f"{SYMPTOM_KR[s]} {txt}")
    return " · ".join(parts)


if __name__ == "__main__":
    from recommendation.retrieval.retriever import Retriever

    r = Retriever(backend="hashing")
    levels = {"dandruff": 1, "hair_loss": 2}
    res = r.retrieve_category(levels, "shampoo", {"age_group": "20대"})
    p = build_category_prompt(res["levels"], {"age_group": "20대"},
                              res["candidates"], "shampoo", pick=3)
    print(p[:1800])
    print("...")
    print(f"\n프롬프트 길이 {len(p):,}자")
    print("\n근거 성분 문구 예시")
    for c in res["candidates"][:3]:
        print(f"  {c['name_clean'][:28]:28s} {evidence_note(c, res['levels']) or '없음'}")
