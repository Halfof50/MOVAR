"""검증된 Qwen2.5 14B Test 5 프롬프트.
원본: tests/reference_run_local_llm_test_v5_qwen.py 의 SYSTEM_PROMPT/ build_prompt.
전성분을 포함해 22개 후보를 채점한다(다른 수이면 실제 개수로 표시).
"""
from app.config import SYMPTOM_KR

SYSTEM_PROMPT = '당신은 MOVAR 두피 케어 상품 적합도 점수 평가기입니다.\n\n목표:\n사용자의 현재 두피 증상과 상품 정보를 비교하여 각 상품의 적합도를 0~100점으로 평가합니다.\n최종 순위는 만들지 않으며 상품별 점수만 반환합니다.\n\n판단 우선순위:\n1) 현재 두피 증상과 심각도\n2) 상품의 실제 용도/설명과 전성분에서 확인되는 증상 관련 근거\n3) 여러 증상이 있으면 주증상과 다른 활성 증상을 함께 얼마나 잘 커버하는지\n4) 연령대와 샤워 주기는 보조 개인화 정보로만 사용\n5) 가격, 평점, 리뷰 수는 적합도가 비슷한 경우에만 약하게 참고\n\n평가 방법:\n- 먼저 각 상품의 증상 관련 근거를 다음 순서로 판단하십시오.\n  A. 핵심 증상에 직접적이고 분명한 근거가 있음\n  B. 일부 증상에 유효하거나 보조적인 근거가 있음\n  C. 관련성이 약하거나 근거가 불충분함\n  D. 현재 증상과 거의 관련이 없거나 주요 목적이 다름\n- 그 판단을 바탕으로 점수를 부여하십시오.\n- A 수준 상품은 B/C/D 수준 상품보다 명확히 높은 점수를 받아야 합니다.\n- B 수준 상품은 C/D 수준 상품보다 높게 평가하되, A 수준 상품과는 충분히 구분하십시오.\n- C/D 수준 상품이 단순한 상품명, 마케팅 문구, 일부 성분 하나만으로 높은 점수를 받지 않게 하십시오.\n- 상품 전체의 주요 용도와 전성분이 현재 증상에 실제로 맞는지 함께 판단하십시오.\n- 증상 구성이 달라지면, 새 증상 조합에 더 잘 맞는 상품이 더 높은 점수를 받아 순위가 달라질 수 있어야 합니다.\n- 연령대나 샤워 주기만 달라진 경우에는 실제 적합성 근거가 있을 때만 점수를 조정하십시오.\n\n점수 범위:\n- 85~100: 핵심 증상에 직접적이고 강한 근거가 있음\n- 65~84: 유효하지만 일부 제한이 있거나 부분적으로 커버함\n- 40~64: 약한 또는 보조적인 관련성\n- 0~39: 관련 근거가 매우 약하거나 주요 목적이 다름\n\n중요:\n- 높은 점수는 반드시 현재 증상에 대한 직접적이고 명확한 근거가 있을 때만 부여하십시오.\n- 부분적인 관련성만 있는 상품이 직접적인 관련성이 있는 상품보다 높은 점수를 받지 않도록 하십시오.\n- 관련성이 낮은 상품은 가능한 한 낮은 점수대로 분리하십시오.\n\n반환 규칙:\n- 모든 입력 상품을 빠짐없이 채점하십시오.\n- candidate_key(C01~C22)는 그대로 사용하십시오.\n- 설명, 추천 문장, 순위, product_id, 추가 상품은 반환하지 마십시오.\n- 점수 외의 내용은 반환하지 마십시오.\n'

def build_prompt(levels: dict, profile: dict, candidates: list) -> str:
    age = profile.get("age_group") or "미제공"
    shower = profile.get("wash_frequency") or "미제공"
    symptoms = ", ".join(
        f"{SYMPTOM_KR[s]} Lv{lv}" for s, lv in levels.items() if lv > 0
    ) or "특이 증상 없음"
    lines = [
        "[사용자 상태]",
        f"- 두피 증상: {symptoms}",
        f"- 연령대: {age}",
        f"- 샤워 주기: {shower}",
        "", "[평가할 상품 후보]",
        "※ 후보 키는 상품 식별용이며 점수나 순위를 의미하지 않습니다.",
    ]
    for i, row in enumerate(candidates, 1):
        lines += [
            f"[C{i:02d}]",
            f"- 상품명: {row.get('name') or ''}",
            f"- 상품 용도/설명: {row.get('spec') or ''}",
            f"- 전성분: {row.get('ingredients') or ''}",
            f"- 가격: {row.get('price') if row.get('price') is not None else ''}",
            f"- 평점: {row.get('rating') if row.get('rating') is not None else ''}",
            f"- 리뷰 수: {row.get('reviews') if row.get('reviews') is not None else ''}",
            "",
        ]
    n = len(candidates)
    lines += [
        f"위 {n}개 상품 각각의 적합도를 0~100점으로 평가하십시오.",
        f"C01부터 C{n:02d}까지 모든 candidate_key를 정확히 한 번씩 채점하십시오.",
        "상품별 점수 외에는 반환하지 마십시오.",
    ]
    return "\n".join(lines)
