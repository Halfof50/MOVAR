"""
samples3.py

개인화 추천 전용 테스트.

목적
────────────────────────────────────────────────────────────
두피 증상과 추천 카테고리는 완전히 동일하게 유지하고
사용자 개인정보만 변경했을 때 최종 추천 순위가
합리적으로 달라지는지 확인한다.

중요:
같은 사용자 입력을 반복했을 때 결과가 달라지는 것은
개인화가 아니라 출력 노이즈다.

원하는 결과:

    같은 증상 + 같은 개인정보
        → 같은 추천

    같은 증상 + 다른 개인정보
        → 개인정보가 실제 상품 선택 근거가 될 경우
          추천 상품 또는 순위가 달라질 수 있음

실행:

    python -m recommendation.samples3

    python -m recommendation.samples3 --model exaone3.5:7.8b

    python -m recommendation.samples3 --backend hashing

    python -m recommendation.samples3 --repeat 3
"""

import argparse

from recommendation.config import CATEGORY_KR, LLM_MODEL
from recommendation.llm.llama_client import LlamaClient
from recommendation.retrieval.retriever import Retriever
from recommendation.service.recommendation_service import RecommendationService


# ============================================================
# 모든 테스트에서 동일하게 사용할 두피 상태
# ============================================================

SCALP = {
    "dandruff": 1,
    "hair_loss": 2,
}

PLAN = ["shampoo"]


# ============================================================
# 개인화 테스트 프로필
# ============================================================

PROFILES = [
    {
        "name": "기준 사용자",
        "profile": {},
        "purpose": "개인정보가 없을 때의 기준 추천",
    },

    {
        "name": "20대 · 하루 1회",
        "profile": {
            "age_group": "20대",
            "wash_frequency": "하루 1회",
        },
        "purpose": "연령대와 일반적인 세정 주기 반영 확인",
    },

    {
        "name": "50대 · 2일 1회",
        "profile": {
            "age_group": "50대 이상",
            "wash_frequency": "2일에 1회",
        },
        "purpose": "연령대와 낮은 세정 빈도 변화 확인",
    },

    {
        "name": "하루 2회 세정",
        "profile": {
            "age_group": "20대",
            "wash_frequency": "하루 2회",
        },
        "purpose": "잦은 세정 정보가 추천에 영향을 주는지 확인",
    },

    {
        "name": "저예산 15,000원",
        "profile": {
            "age_group": "20대",
            "wash_frequency": "하루 1회",
            "max_price": 15000,
        },
        "purpose": "낮은 가격 상한 반영 확인",
    },

    {
        "name": "중간예산 30,000원",
        "profile": {
            "age_group": "20대",
            "wash_frequency": "하루 1회",
            "max_price": 30000,
        },
        "purpose": "가격 범위 확대 시 추천 변화 확인",
    },

    {
        "name": "고예산 60,000원",
        "profile": {
            "age_group": "20대",
            "wash_frequency": "하루 1회",
            "max_price": 60000,
        },
        "purpose": "가격 제한이 느슨할 때 추천 변화 확인",
    },

    {
        "name": "복합 프로필 A",
        "profile": {
            "age_group": "20대",
            "wash_frequency": "하루 2회",
            "max_price": 20000,
        },
        "purpose": "여러 개인정보가 동시에 주어졌을 때 개인화 확인",
    },

    {
        "name": "복합 프로필 B",
        "profile": {
            "age_group": "50대 이상",
            "wash_frequency": "2일에 1회",
            "max_price": 50000,
        },
        "purpose": "A와 반대 성격의 개인정보에서 추천 변화 확인",
    },
]


# ============================================================
# 출력용 함수
# ============================================================

def profile_line(profile: dict) -> str:

    if not profile:
        return "등록 정보 없음"

    bits = []

    if profile.get("age_group"):
        bits.append(profile["age_group"])

    if profile.get("wash_frequency"):
        bits.append(profile["wash_frequency"])

    if profile.get("max_price"):
        bits.append(f"{profile['max_price']:,}원 이하")

    return " · ".join(bits)


def recommendation_ids(result: dict) -> dict:
    """
    카테고리별 추천 product_id 목록 반환

    예:
    {
        "shampoo": [81, 79, 53]
    }
    """

    result_ids = {}

    for cat, block in result["by_category"].items():

        result_ids[cat] = [
            r["product_id"]
            for r in block["recommendations"]
        ]

    return result_ids


def recommendation_sets(result: dict) -> dict:
    """
    순서를 무시한 상품 집합.
    상품 구성 자체가 달라졌는지 확인할 때 사용.
    """

    return {
        cat: set(ids)
        for cat, ids in recommendation_ids(result).items()
    }


def print_recommendations(result: dict):

    for cat, block in result["by_category"].items():

        validation = block["validation"]

        flags = []

        if validation.get("dropped_unknown_id"):
            flags.append(
                f"허위id {len(validation['dropped_unknown_id'])}"
            )

        if validation.get("dropped_wrong_category"):
            flags.append(
                f"타카테고리 "
                f"{len(validation['dropped_wrong_category'])}"
            )

        if validation.get("filled_from_retrieval"):
            flags.append(
                f"검색순위로채움 "
                f"{validation['filled_from_retrieval']}"
            )

        print(
            f"    ── {CATEGORY_KR[cat]} "
            f"후보 {block['candidate_count']}개"
            f"{' / ' + ' / '.join(flags) if flags else ''}"
        )

        for r in block["recommendations"]:

            print(
                f"       {r['category_rank']}. "
                f"{r['product_name'][:40]}"
            )

            print(
                f"          product_id={r['product_id']} "
                f"/ 검색{r['retrieval_rank']}위 "
                f"/ {r['price']:,}원"
            )

            if r.get("personalization_factors"):
                print(
                    "          개인화 요소:",
                    ", ".join(r["personalization_factors"])
                )

            if r.get("reason"):
                print(
                    f"          이유: {r['reason']}"
                )

        print()


# ============================================================
# 기준 결과와 비교
# ============================================================

def compare_with_baseline(baseline: dict, current: dict):

    base_ids = recommendation_ids(baseline)
    current_ids = recommendation_ids(current)

    messages = []

    for cat in current_ids:

        before = base_ids.get(cat, [])
        after = current_ids.get(cat, [])

        # 완전히 동일
        if before == after:

            messages.append(
                f"{CATEGORY_KR[cat]}: 완전히 동일"
            )

            continue

        # 상품 구성은 같은데 순서만 변경
        if set(before) == set(after):

            messages.append(
                f"{CATEGORY_KR[cat]}: 상품은 같고 순위 변경"
            )

            continue

        # 실제 추천 상품 변경
        removed = [
            pid for pid in before
            if pid not in after
        ]

        added = [
            pid for pid in after
            if pid not in before
        ]

        messages.append(
            f"{CATEGORY_KR[cat]}: 추천 상품 변경 "
            f"(제외 {removed or '-'} / 추가 {added or '-'})"
        )

    return messages


# ============================================================
# 동일 입력 반복 안정성 테스트
# ============================================================

def repeat_test(
    svc,
    repeat_count,
    use_llm=True,
):

    print()
    print("=" * 72)
    print("[반복 안정성 테스트]")
    print("동일 증상 + 동일 개인정보를 반복 입력합니다.")
    print()

    profile = {
        "age_group": "30대",
        "wash_frequency": "하루 1회",
        "max_price": 30000,
    }

    runs = []

    for i in range(repeat_count):

        result = svc.recommend(
            SCALP,
            profile,
            plan=PLAN,
            use_llm=use_llm,
        )

        ids = recommendation_ids(result)

        runs.append(ids)

        print(
            f"    {i + 1}회차:",
            ids
        )

    stable = all(
        run == runs[0]
        for run in runs[1:]
    )

    print()

    if stable:
        print(
            "    PASS — 동일 입력에서 추천 결과가 "
            "모두 동일합니다."
        )

    else:
        print(
            "    WARNING — 동일 입력인데 추천 결과가 "
            "달라졌습니다."
        )

        print(
            "    → 개인화가 아니라 LLM 출력 노이즈 또는 "
            "후보 순서 영향을 확인해야 합니다."
        )

    return stable


# ============================================================
# 메인
# ============================================================

def main(argv=None):

    ap = argparse.ArgumentParser()

    ap.add_argument(
        "--model",
        default=LLM_MODEL,
    )

    ap.add_argument(
        "--backend",
        default="auto",
        choices=["auto", "st", "hashing"],
    )

    ap.add_argument(
        "--no-llm",
        dest="use_llm",
        action="store_false",
        default=True,
    )

    ap.add_argument(
        "--repeat",
        type=int,
        default=3,
        help="동일 입력 반복 테스트 횟수",
    )

    args = ap.parse_args(argv)

    retriever = Retriever(
        backend=args.backend
    )

    svc = RecommendationService(
        retriever=retriever,
        llm=LlamaClient(model=args.model),
    )

    # --------------------------------------------------------
    # 모델 확인
    # --------------------------------------------------------

    if args.use_llm:

        ok, msg = svc.llm.available()

        print(
            f"모델 {args.model} — "
            f"{'사용 가능' if ok else '사용 불가'}"
        )

        if not ok:
            print(
                f"  {msg.splitlines()[0]}"
            )

    print()

    print("=" * 72)
    print("개인화 추천 테스트")
    print("=" * 72)

    print(
        "공통 두피:",
        "비듬 1단계 / 탈모 2단계"
    )

    print(
        "공통 카테고리:",
        "샴푸"
    )

    print()

    results = []

    # --------------------------------------------------------
    # 개인화 테스트 실행
    # --------------------------------------------------------

    for i, case in enumerate(PROFILES, start=1):

        print("=" * 72)

        print(
            f"[{i}] {case['name']}"
        )

        print(
            f"    사용자: "
            f"{profile_line(case['profile'])}"
        )

        print(
            f"    테스트 목적: "
            f"{case['purpose']}"
        )

        result = svc.recommend(
            SCALP,
            case["profile"],
            plan=PLAN,
            use_llm=args.use_llm,
        )

        results.append(
            (case, result)
        )

        print(
            f"    LLM 호출 {result['llm_calls']}회 "
            f"/ {result['timing_ms']['total_ms']}ms"
        )

        print_recommendations(result)

    # --------------------------------------------------------
    # 기준 사용자와 자동 비교
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("개인화 결과 비교")
    print("=" * 72)

    baseline_case, baseline = results[0]

    print()
    print(
        f"기준: {baseline_case['name']}"
    )

    print(
        "추천:",
        recommendation_ids(baseline)
    )

    changed_count = 0
    ranking_only_count = 0
    identical_count = 0

    for case, result in results[1:]:

        comparison = compare_with_baseline(
            baseline,
            result,
        )

        print()
        print(
            f"[{case['name']}]"
        )

        print(
            "추천:",
            recommendation_ids(result)
        )

        for msg in comparison:

            print(
                "   →",
                msg
            )

            if "추천 상품 변경" in msg:
                changed_count += 1

            elif "순위 변경" in msg:
                ranking_only_count += 1

            elif "완전히 동일" in msg:
                identical_count += 1

    # --------------------------------------------------------
    # 반복 안정성
    # --------------------------------------------------------

    stable = repeat_test(
        svc,
        args.repeat,
        use_llm=args.use_llm,
    )

    # --------------------------------------------------------
    # 최종 요약
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("최종 검증 요약")
    print("=" * 72)

    print(
        f"추천 상품 자체 변경 : "
        f"{changed_count}건"
    )

    print(
        f"상품은 같고 순위 변경: "
        f"{ranking_only_count}건"
    )

    print(
        f"기준과 완전히 동일   : "
        f"{identical_count}건"
    )

    print()

    if changed_count == 0 and ranking_only_count == 0:

        print(
            "WARNING — 개인정보를 변경했지만 "
            "모든 추천 결과가 기준 사용자와 동일합니다."
        )

        print(
            "→ 개인화 LLM이 개인정보를 실제 랭킹에 "
            "사용하는지 확인하세요."
        )

    else:

        print(
            "개인정보 변화에 따라 추천 구성 또는 "
            "순위 변화가 확인되었습니다."
        )

    if stable:

        print(
            "PASS — 동일 사용자 반복 결과는 안정적입니다."
        )

    else:

        print(
            "WARNING — 동일 사용자 반복 결과에 "
            "노이즈가 있습니다."
        )

    print()
    print("해석할 때 주의:")
    print(
        "  • 결과가 다르다고 무조건 개인화 성공은 아닙니다."
    )
    print(
        "  • 추천 이유가 변경된 개인정보와 논리적으로 "
        "연결되는지도 함께 확인해야 합니다."
    )
    print(
        "  • 연령대처럼 상품 DB에 직접 대응 정보가 부족한 "
        "항목은 결과가 같아도 반드시 오류는 아닙니다."
    )
    print(
        "  • 동일 입력 반복 결과는 가능한 한 같아야 합니다."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())