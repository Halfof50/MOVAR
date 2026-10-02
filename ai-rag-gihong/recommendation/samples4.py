"""
samples4.py

LLM 순위 판단력 전용 테스트.

목적
────────────────────────────────────────────────────────────
현재 구조에서는:
    RAG → 후보 검색 → LLM이 Top N 순위 + decision_factors 결정
    → 추천 이유는 코드가 실제 데이터로 생성

따라서 이 파일은 "추천 이유 문장"이 아니라
LLM이 후보 순위를 얼마나 일관되고 합리적으로 정하는지를 본다.

자동 점검 항목
────────────────────────────────────────────────────────────
1. 최고 Level 증상이 decision_factors에서 누락되는가
2. 사용자가 가지지 않은 증상/정보를 decision_factors에 넣는가
3. 동일 입력 반복 시 Top3 순위가 흔들리는가
4. 검색 1위/상위 후보만 기계적으로 고르는 경향이 강한가
5. 상위 추천 상품의 활성 증상 근거가 지나치게 약한가
6. 후보 밖 product_id, fallback 등이 발생하는가

주의
────────────────────────────────────────────────────────────
이 테스트는 "절대 정답 채점기"가 아니다.
성분 근거 개수가 많다고 항상 더 좋은 상품인 것은 아니므로,
근거 개수 관련 평가는 FAIL이 아니라 WARNING으로 본다.

실행 예시
────────────────────────────────────────────────────────────
python -m recommendation.samples4

python -m recommendation.samples4 --model llama3.1:8b
python -m recommendation.samples4 --model gemma3:12b

특정 케이스:
python -m recommendation.samples4 --case 4

반복 횟수:
python -m recommendation.samples4 --repeat 5

LLM 없이 검색 결과 확인:
python -m recommendation.samples4 --no-llm
"""

import argparse
from collections import Counter

from recommendation.config import CATEGORY_KR, LLM_MODEL, SYMPTOM_KR
from recommendation.llm.llama_client import LlamaClient
from recommendation.retrieval.retriever import Retriever
from recommendation.service.recommendation_service import RecommendationService


CASES = [
    (
        "단일 고강도 — 탈모3",
        {"hair_loss": 3},
        {},
        ["shampoo"],
    ),
    (
        "단일 고강도 — 비듬3",
        {"dandruff": 3},
        {},
        ["shampoo"],
    ),
    (
        "레벨 차이 — 탈모3 + 비듬1",
        {"hair_loss": 3, "dandruff": 1},
        {},
        ["shampoo"],
    ),
    (
        "레벨 차이 — 각질3 + 피지2 + 비듬1",
        {
            "micro_keratin": 3,
            "excess_sebum": 2,
            "dandruff": 1,
        },
        {},
        ["shampoo"],
    ),
    (
        "레벨 차이 — 홍반3 + 농포1",
        {
            "follicular_erythema": 3,
            "follicular_pustule": 1,
        },
        {},
        ["shampoo"],
    ),
    (
        "동률 — 피지2 + 비듬2",
        {"excess_sebum": 2, "dandruff": 2},
        {},
        ["shampoo"],
    ),
    (
        "동률 — 홍반2 + 농포2",
        {
            "follicular_erythema": 2,
            "follicular_pustule": 2,
        },
        {},
        ["shampoo"],
    ),
    (
        "다증상 — 6개 모두1",
        {
            "micro_keratin": 1,
            "excess_sebum": 1,
            "follicular_erythema": 1,
            "follicular_pustule": 1,
            "dandruff": 1,
            "hair_loss": 1,
        },
        {},
        ["shampoo"],
    ),
    (
        "가격 제약 — 탈모2 / 15000원",
        {"hair_loss": 2},
        {"max_price": 15000},
        ["shampoo"],
    ),
    (
        "스케일러 — 각질3",
        {"micro_keratin": 3},
        {},
        ["scaler"],
    ),
    (
        "트리트먼트 — 홍반3",
        {"follicular_erythema": 3},
        {},
        ["treatment"],
    ),
    (
        "토닉 — 탈모3",
        {"hair_loss": 3},
        {},
        ["tonic"],
    ),
]


def describe(levels: dict) -> str:
    active = [
        f"{SYMPTOM_KR.get(k, k)} {v}"
        for k, v in levels.items()
        if v > 0
    ]
    return ", ".join(active) or "전 증상 0단계"


def profile_line(profile: dict) -> str:
    if not profile:
        return "등록 정보 없음"

    out = []

    if profile.get("age_group"):
        out.append(str(profile["age_group"]))

    if profile.get("wash_frequency"):
        out.append(str(profile["wash_frequency"]))

    if profile.get("max_price"):
        out.append(f"{int(profile['max_price']):,}원 이하")

    return " · ".join(out) if out else str(profile)


def active_symptoms(levels: dict) -> list:
    return [s for s, lv in levels.items() if lv > 0]


def highest_level_symptoms(levels: dict) -> list:
    active = active_symptoms(levels)

    if not active:
        return []

    high = max(levels[s] for s in active)

    return [s for s in active if levels[s] == high]


def evidence_for(rec: dict, symptom: str) -> list:
    ev = rec.get("score_evidence", {}) or {}
    return list(ev.get(symptom) or [])


def symptom_score(rec: dict, symptom: str) -> float:
    sc = rec.get("symptom_scores", {}) or {}

    try:
        return float(sc.get(symptom, 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def total_active_evidence_count(rec: dict, levels: dict) -> int:
    total = 0

    for s in active_symptoms(levels):
        total += len(evidence_for(rec, s))

    return total


def weighted_symptom_score(rec: dict, levels: dict) -> float:
    total = 0.0

    for s in active_symptoms(levels):
        total += symptom_score(rec, s) * float(levels.get(s, 0))

    return total


def allowed_decision_factors(levels: dict, profile: dict) -> set:
    allowed = set(active_symptoms(levels))

    for key, value in profile.items():
        if value not in (None, "", [], {}):
            allowed.add(key)

    return allowed


def validate_decision_factors(rec: dict, levels: dict, profile: dict) -> list:
    warnings = []

    factors = set(rec.get("decision_factors") or [])
    allowed = allowed_decision_factors(levels, profile)

    invalid = sorted(factors - allowed)

    if invalid:
        warnings.append(
            "허용되지 않은 decision_factors: "
            + ", ".join(invalid)
        )

    high_syms = highest_level_symptoms(levels)

    for s in high_syms:
        has_support = (
            symptom_score(rec, s) > 0
            or bool(evidence_for(rec, s))
        )

        if has_support and s not in factors:
            warnings.append(
                f"최고 레벨 증상 선택요소 누락: "
                f"{SYMPTOM_KR.get(s, s)}(Level {levels[s]})"
            )

    return warnings


def validate_rank_strength(recs: list, levels: dict) -> list:
    warnings = []

    if len(recs) < 2:
        return warnings

    for i in range(len(recs) - 1):
        upper = recs[i]
        lower = recs[i + 1]

        upper_weighted = weighted_symptom_score(upper, levels)
        lower_weighted = weighted_symptom_score(lower, levels)

        upper_ev = total_active_evidence_count(upper, levels)
        lower_ev = total_active_evidence_count(lower, levels)

        if (
            upper_weighted < lower_weighted
            and upper_ev + 2 <= lower_ev
        ):
            warnings.append(
                f"{i + 1}위 상품의 증상 근거가 "
                f"{i + 2}위보다 현저히 약함 "
                f"(weighted {upper_weighted:.2f} < {lower_weighted:.2f}, "
                f"evidence {upper_ev} < {lower_ev})"
            )

    return warnings


def retrieval_bias_stats(recs: list) -> dict:
    ranks = [
        int(r.get("retrieval_rank"))
        for r in recs
        if r.get("retrieval_rank") is not None
    ]

    if not ranks:
        return {"ranks": [], "top3_count": 0, "avg": None}

    return {
        "ranks": ranks,
        "top3_count": sum(1 for r in ranks if r <= 3),
        "avg": sum(ranks) / len(ranks),
    }


def signature(out: dict) -> tuple:
    rows = []

    for cat, block in out["by_category"].items():
        ids = tuple(
            r["product_id"]
            for r in block["recommendations"]
        )
        rows.append((cat, ids))

    return tuple(rows)


def print_one_result(out: dict, levels: dict, profile: dict):
    all_warnings = []
    bias_info = []

    for cat, block in out["by_category"].items():
        recs = block["recommendations"]
        validation = block.get("validation") or {}

        print(
            f"      ── {CATEGORY_KR[cat]} "
            f"(후보 {block['candidate_count']}개)"
        )

        if validation.get("dropped_unknown_id"):
            msg = (
                f"후보 밖 product_id "
                f"{len(validation['dropped_unknown_id'])}건"
            )
            print(f"         ⚠ {msg}")
            all_warnings.append(msg)

        if validation.get("dropped_wrong_category"):
            msg = (
                f"타 카테고리 ID "
                f"{len(validation['dropped_wrong_category'])}건"
            )
            print(f"         ⚠ {msg}")
            all_warnings.append(msg)

        if validation.get("filled_from_retrieval"):
            msg = (
                f"LLM 결과 부족 → 검색순위 fallback "
                f"{validation['filled_from_retrieval']}건"
            )
            print(f"         ⚠ {msg}")
            all_warnings.append(msg)

        for r in recs:
            factors = r.get("decision_factors") or []

            weighted = weighted_symptom_score(r, levels)
            ev_count = total_active_evidence_count(r, levels)

            print(
                f"         {r['category_rank']}. "
                f"{r['product_name'][:42]}"
            )

            print(
                f"            product_id={r['product_id']} "
                f"/ 검색{r.get('retrieval_rank', '?')}위 "
                f"/ weighted={weighted:.2f} "
                f"/ evidence={ev_count}"
            )

            print(
                "            선택요소 — "
                + (", ".join(factors) if factors else "없음")
            )

            supports = []

            for s in active_symptoms(levels):
                score = symptom_score(r, s)
                ev = len(evidence_for(r, s))

                if score > 0 or ev > 0:
                    supports.append(
                        f"{SYMPTOM_KR.get(s, s)}:"
                        f"score={score:.1f}/evidence={ev}"
                    )

            if supports:
                print(
                    "            실제 근거 — "
                    + " | ".join(supports)
                )

            factor_warnings = validate_decision_factors(
                r,
                levels,
                profile,
            )

            for warning in factor_warnings:
                print(f"            ⚠ {warning}")
                all_warnings.append(
                    f"{CATEGORY_KR[cat]} / "
                    f"{r['product_id']} / {warning}"
                )

        rank_warnings = validate_rank_strength(recs, levels)

        for warning in rank_warnings:
            print(f"         ⚠ 순위주의: {warning}")
            all_warnings.append(
                f"{CATEGORY_KR[cat]} / {warning}"
            )

        bias = retrieval_bias_stats(recs)
        bias_info.append((cat, bias))

        if bias["ranks"]:
            print(
                f"         검색순위 사용 분포: {bias['ranks']} "
                f"/ 검색 Top3 포함 {bias['top3_count']}개 "
                f"/ 평균 검색순위 {bias['avg']:.2f}"
            )

        print()

    return all_warnings, bias_info


def main(argv=None):
    ap = argparse.ArgumentParser()

    ap.add_argument(
        "--case",
        type=int,
        help="1부터 시작하는 케이스 번호. 생략하면 전체",
    )

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
        "--repeat",
        type=int,
        default=3,
        help="각 케이스 반복 횟수. 기본 3회",
    )

    ap.add_argument(
        "--no-llm",
        dest="use_llm",
        action="store_false",
        default=True,
    )

    args = ap.parse_args(argv)

    svc = RecommendationService(
        retriever=Retriever(backend=args.backend),
        llm=LlamaClient(model=args.model),
    )

    print("=" * 72)
    print("LLM 순위 판단력 테스트")
    print("=" * 72)
    print(f"모델: {args.model}")
    print(f"반복: 각 케이스 {args.repeat}회")
    print()

    if args.use_llm:
        ok, msg = svc.llm.available()

        print(
            f"모델 상태: "
            f"{'사용 가능' if ok else '사용 불가'}"
        )

        if not ok:
            print(f"  {msg.splitlines()[0]}")

        print()

    cases = CASES if args.case is None else [CASES[args.case - 1]]
    start = 1 if args.case is None else args.case

    global_warning_counter = Counter()

    total_cases = 0
    stable_cases = 0

    retrieval_rank_counter = Counter()
    retrieval_top3_picks = 0
    retrieval_total_picks = 0

    for idx, (label, levels, profile, plan) in enumerate(
        cases,
        start=start,
    ):
        total_cases += 1

        print("=" * 72)
        print(f"[{idx}] {label}")
        print(f"    두피: {describe(levels)}")
        print(f"    사용자: {profile_line(profile)}")
        print(f"    카테고리: {[CATEGORY_KR[c] for c in plan]}")
        print()

        runs = []
        case_warnings = []

        for run_idx in range(args.repeat):
            out = svc.recommend(
                levels,
                profile,
                plan=plan,
                use_llm=args.use_llm,
            )

            runs.append(signature(out))

            print(
                f"    실행 {run_idx + 1}/{args.repeat} "
                f"— {out['timing_ms']['total_ms']}ms"
            )

            warnings, biases = print_one_result(
                out,
                levels,
                profile,
            )

            case_warnings.extend(warnings)

            for _, bias in biases:
                for rank in bias["ranks"]:
                    retrieval_rank_counter[rank] += 1
                    retrieval_total_picks += 1

                    if rank <= 3:
                        retrieval_top3_picks += 1

        stable = all(
            run == runs[0]
            for run in runs[1:]
        )

        if stable:
            stable_cases += 1

        print("    반복 안정성:")
        print(
            "      "
            + (
                "PASS — 모든 실행의 추천 순위가 동일"
                if stable
                else "WARNING — 동일 입력에서 추천 순위가 흔들림"
            )
        )

        if case_warnings:
            print(f"    판단 경고: {len(case_warnings)}건")
        else:
            print("    판단 경고: 없음")

        for warning in case_warnings:
            if "최고 레벨 증상 선택요소 누락" in warning:
                global_warning_counter[
                    "최고 레벨 증상 decision_factors 누락"
                ] += 1

            elif "허용되지 않은 decision_factors" in warning:
                global_warning_counter[
                    "허용되지 않은 decision_factors"
                ] += 1

            elif "후보 밖 product_id" in warning:
                global_warning_counter[
                    "후보 밖 product_id"
                ] += 1

            elif "fallback" in warning:
                global_warning_counter[
                    "검색순위 fallback"
                ] += 1

            elif "증상 근거가" in warning:
                global_warning_counter[
                    "순위 근거 약함"
                ] += 1

        print()

    print("=" * 72)
    print("전체 모델 평가 요약")
    print("=" * 72)

    print(
        f"반복 안정성: "
        f"{stable_cases}/{total_cases} 케이스 PASS"
    )

    if total_cases:
        print(
            f"안정성 비율: "
            f"{stable_cases / total_cases * 100:.1f}%"
        )

    print()

    if global_warning_counter:
        print("판단 경고:")
        for key, count in global_warning_counter.most_common():
            print(f"  - {key}: {count}건")
    else:
        print("판단 경고: 없음")

    print()

    if retrieval_total_picks:
        ratio = (
            retrieval_top3_picks
            / retrieval_total_picks
            * 100
        )

        print("검색순위 편향 참고:")
        print(
            f"  전체 추천 선택 {retrieval_total_picks}건 중 "
            f"검색 Top3 상품 선택 {retrieval_top3_picks}건 "
            f"({ratio:.1f}%)"
        )

        common = retrieval_rank_counter.most_common(8)

        print(
            "  가장 자주 선택한 검색순위:",
            ", ".join(
                f"{rank}위={count}회"
                for rank, count in common
            ),
        )

        print(
            "  ※ Top3 비율이 높다는 이유만으로 오류는 아니다."
        )
        print(
            "     모델 비교 시 한 모델이 지나치게 "
            "검색 상위권만 복사하는지 보는 참고 지표다."
        )

    print()
    print("모델 비교할 때 볼 핵심")
    print("  1. 반복 안정성이 더 높은가")
    print("  2. 최고 Level 증상 누락이 더 적은가")
    print("  3. 존재하지 않는 decision_factors가 없는가")
    print("  4. fallback/허위 ID가 없는가")
    print("  5. 검색순위를 단순 복사하지 않고 다양한 후보를 비교하는가")
    print("  6. 응답시간이 실사용 가능한 수준인가")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
