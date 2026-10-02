"""
추천 평가 프롬프트.

LLM 역할은 '후보별 적합도 평가'만 담당한다.
- product_id / 상품명 / 최종 순위는 LLM이 만들지 않는다.
- 후보 1~N 각각에 대해 0~100점과 decision_factors만 반환한다.
- 실제 product_id 매핑, Top3 정렬, 추천 이유 생성은 Python이 담당한다.
"""

from recommendation.config import CATEGORY_KR, LEVEL_KR, PICK_PER_CATEGORY, SYMPTOMS, SYMPTOM_KR

PROFILE_LABEL = {
    "age_group": "연령대",
    "wash_frequency": "머리 감는 주기",
    "food_allergies": "음식 알레르기",
    "avoid_ingredients": "기피 성분",
    "max_price": "희망 가격 상한",
    "preferred_categories": "선호 제품 유형",
    "concerns": "직접 입력한 불편 사항",
}

# 기존 코드와의 호환을 위해 문자열 상수는 남겨 둔다.
OUTPUT_FORMAT = """[출력 형식]\n{\n  \"evaluations\": [\n    {\"candidate_no\": 1, \"score\": 0, \"decision_factors\": [\"hair_loss\"]}\n  ]\n}"""
CATEGORY_OUTPUT_FORMAT = OUTPUT_FORMAT
RULES = "LLM은 후보별 점수와 판단요소만 반환한다."


def format_symptoms(levels: dict) -> str:
    return "\n".join(
        f"- {SYMPTOM_KR[s]} ({s}): {levels.get(s, 0)}단계 {LEVEL_KR[levels.get(s, 0)]}"
        for s in SYMPTOMS
    )


def format_profile(profile: dict) -> str:
    if not profile:
        return "- 등록된 정보 없음"
    lines = []
    for key, label in PROFILE_LABEL.items():
        v = profile.get(key)
        if v in (None, "", [], {}):
            continue
        if isinstance(v, (list, tuple)):
            v = ", ".join(str(x) for x in v)
        if key == "max_price":
            v = f"{int(v):,}원"
        lines.append(f"- {label}: {v}")
    return "\n".join(lines) or "- 등록된 정보 없음"


def format_candidate(c: dict, levels: dict, include_full_ingredients: bool = False) -> str:
    """후보 하나를 평가에 필요한 사실만 보여준다."""
    lines = [
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
        f"평점: {rating} / 리뷰 {c.get('reviews', 0):,}건"
        if rating else f"평점: 미상 / 리뷰 {c.get('reviews', 0):,}건"
    )

    sc = c.get("symptom_scores", {}) or {}
    ev = c.get("score_evidence", {}) or {}
    active = [s for s in SYMPTOMS if levels.get(s, 0) > 0]

    if active:
        lines.append("활성 증상별 성분 근거:")
        for s in active:
            score = float(sc.get(s, 0) or 0)
            evidence = ", ".join(ev.get(s) or []) if score > 0 else "없음"
            lines.append(
                f"- {SYMPTOM_KR[s]}(Level {levels[s]}): "
                f"성분적합도 {score:.1f} / 근거 {evidence}"
            )

    # 가격은 서비스에서 hard filter가 적용되지만, 사용자의 가격 조건을 판단요소로
    # 기록할 수 있도록 후보 가격 자체는 전달한다.
    lines.append(f"RAG 검색 유사도: {float(c.get('similarity', 0) or 0):.3f}")

    if include_full_ingredients:
        lines.append(f"전체 전성분: {c.get('ingredients', '')}")

    return "\n".join(lines)


def _allowed_factor_text(levels: dict, profile: dict) -> str:
    factors = [s for s in SYMPTOMS if levels.get(s, 0) > 0]
    for key, value in (profile or {}).items():
        if value not in (None, "", [], {}) and key in PROFILE_LABEL:
            factors.append(key)
    return ", ".join(factors) if factors else "없음"


def build_category_prompt(symptoms: dict, profile: dict, candidates: list,
                          category: str, pick: int = PICK_PER_CATEGORY,
                          include_full_ingredients: bool = False,
                          shuffle: bool = None,
                          seed: int = 0) -> str:
    """
    카테고리별 후보 전체를 평가한다.

    중요: candidate_no는 Python 리스트 위치와 정확히 대응해야 하므로
    이 모드에서는 후보 순서를 섞지 않는다. shuffle 인자는 호환성 때문에만 남겨 둔다.
    """
    items = list(candidates)
    kr = CATEGORY_KR.get(category, category)

    blocks = "\n\n".join(
        f"[후보 {i}]\n" + format_candidate(c, symptoms, include_full_ingredients)
        for i, c in enumerate(items, start=1)
    )

    allowed = _allowed_factor_text(symptoms, profile or {})
    n = len(items)

    return f"""너는 두피 케어 상품 후보를 비교하는 평가자다.
후보는 모두 {kr}이며, 최종 선택과 정렬은 Python 코드가 한다.
너는 상품을 추천하거나 product_id를 출력하지 말고, 후보 {n}개 각각의 적합도만 평가한다.

[두피 분석 결과]
{format_symptoms(symptoms)}

[사용자 정보]
{format_profile(profile or {})}

[{kr} 후보 {n}개]
{blocks}

[평가 규칙]
1. 후보 1부터 후보 {n}까지 빠짐없이 정확히 한 번씩 평가한다.
2. candidate_no는 위에 표시된 1~{n} 번호만 사용한다.
3. score는 0~100 정수다. 높을수록 현재 사용자에게 더 적합하다.
4. 증상 Level이 높을수록 더 중요하게 반영한다.
5. 성분 적합도와 실제 근거 성분이 있는 증상을 우선한다.
6. RAG 검색 유사도는 참고값일 뿐 최종 점수를 그대로 결정하지 않는다.
7. 사용자 정보는 상품과 실제로 관련 있을 때만 반영한다.
8. 제공되지 않은 효능이나 성분 관계를 새로 추론하지 않는다.
9. decision_factors에는 실제 점수 판단에 사용한 항목만 넣는다.
10. decision_factors에 사용할 수 있는 값: {allowed}
11. 상품명, product_id, 추천 이유 문장, 최종 순위는 출력하지 않는다.
12. JSON만 출력한다.

[출력 형식]
{{
  "evaluations": [
    {{"candidate_no": 1, "score": 82, "decision_factors": ["hair_loss"]}},
    {{"candidate_no": 2, "score": 71, "decision_factors": ["dandruff"]}}
  ]
}}

반드시 후보 1부터 후보 {n}까지 총 {n}개 평가를 반환한다.
"""


def build_recommendation_prompt(symptoms: dict, profile: dict, candidates: list,
                                include_full_ingredients: bool = False) -> str:
    """구버전 호출부 호환용. 카테고리를 첫 후보에서 가져와 동일 평가 프롬프트를 만든다."""
    category = candidates[0].get("category") if candidates else "product"
    return build_category_prompt(
        symptoms, profile, candidates, category,
        pick=min(3, len(candidates)),
        include_full_ingredients=include_full_ingredients,
    )


def evidence_note(cand: dict, levels: dict) -> str:
    """DB/규칙에서 확인된 실제 증상별 근거 성분만 문자열로 만든다."""
    sc = cand.get("symptom_scores", {}) or {}
    ev = cand.get("score_evidence", {}) or {}
    parts = []

    for s in sorted(SYMPTOMS, key=lambda x: -levels.get(x, 0)):
        if levels.get(s, 0) <= 0 or float(sc.get(s, 0) or 0) <= 0:
            continue
        vals = [str(x) for x in (ev.get(s) or []) if x]
        if vals:
            parts.append(f"{SYMPTOM_KR[s]}: {', '.join(vals)}")

    return " · ".join(parts)


if __name__ == "__main__":
    from recommendation.retrieval.retriever import Retriever

    r = Retriever(backend="hashing")
    levels = {"dandruff": 1, "hair_loss": 2}
    res = r.retrieve_category(levels, "shampoo", {"age_group": "20대"})
    print(build_category_prompt(levels, {"age_group": "20대"}, res["candidates"], "shampoo")[:3000])
