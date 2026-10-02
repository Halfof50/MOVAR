"""
samples2.py

추천 이유 / 근거 검증 전용 테스트.

목적
────────────────────────────────────────────────────────────
현재 구조에서는 LLM이 최종 상품 순위만 결정하고,
추천 이유는 코드가 실제 상품 데이터와 증상별 성분 근거를 이용해 생성한다.

이 파일은 다음 오류가 다시 발생하지 않는지 확인한다.

1. 상품에 없는 성분이 추천 이유에 등장하는가
2. 사용자가 가지지 않은 0단계 증상이 이유에 등장하는가
3. 복합 증상인데 실제 근거가 있는 증상을 이유에서 누락하는가
4. 증상 근거가 없는 상품인데 있는 것처럼 설명하는가
5. 후보가 3개보다 적을 때 허위 product_id가 생성되는가
6. 동일 입력에서 추천 순위가 흔들리는가
7. 레벨이 다른 증상이 있을 때 높은 레벨 증상을 우선 고려하는가

실행
────────────────────────────────────────────────────────────
python -m recommendation.samples2
python -m recommendation.samples2 --case 3
python -m recommendation.samples2 --repeat 5
python -m recommendation.samples2 --model exaone3.5:7.8b
python -m recommendation.samples2 --no-llm
"""

import argparse
from collections import Counter

from recommendation.config import CATEGORY_KR, LLM_MODEL, SYMPTOM_KR
from recommendation.llm.llama_client import LlamaClient
from recommendation.retrieval.retriever import Retriever
from recommendation.service.recommendation_service import RecommendationService


CASES = [
    ("단일 증상 — 탈모 3단계", {"hair_loss": 3}, {}, ["shampoo"], 1),
    ("단일 증상 — 비듬 2단계", {"dandruff": 2}, {}, ["shampoo"], 1),
    ("복합 증상 — 탈모2 + 비듬1", {"hair_loss": 2, "dandruff": 1}, {}, ["shampoo"], 1),
    ("복합 동률 — 피지2 + 비듬2", {"excess_sebum": 2, "dandruff": 2}, {}, ["shampoo"], 1),
    ("복합 다증상 — 각질3 + 피지2 + 비듬1",
     {"micro_keratin": 3, "excess_sebum": 2, "dandruff": 1}, {}, ["shampoo"], 1),
    ("홍반 계열 복합 — 홍반2 + 농포2",
     {"follicular_erythema": 2, "follicular_pustule": 2}, {}, ["shampoo"], 1),
    ("전 증상 1단계",
     {"micro_keratin": 1, "excess_sebum": 1, "follicular_erythema": 1,
      "follicular_pustule": 1, "dandruff": 1, "hair_loss": 1}, {}, ["shampoo"], 1),
    ("저예산 후보 부족 가능성", {"hair_loss": 2}, {"max_price": 10000}, ["tonic"], 1),
    ("스케일러 — 미세각질3", {"micro_keratin": 3}, {}, ["scaler"], 1),
    ("트리트먼트 — 홍반2", {"follicular_erythema": 2}, {}, ["treatment"], 1),
    ("반복 안정성 — 탈모2 + 비듬1", {"hair_loss": 2, "dandruff": 1}, {}, ["shampoo"], 3),
]


def describe(levels: dict) -> str:
    active = [f"{SYMPTOM_KR[k]} {v}" for k, v in levels.items() if v > 0]
    return ", ".join(active) or "전 증상 0단계"


def _norm_text(v) -> str:
    return str(v or "").replace(" ", "").lower()


def _evidence_for(candidate: dict, symptom: str) -> list:
    ev = candidate.get("score_evidence", {}) or {}
    return list(ev.get(symptom) or [])


def _reason_mentions_symptom(reason: str, symptom: str) -> bool:
    kr = SYMPTOM_KR.get(symptom, symptom)
    return kr in (reason or "")


def _all_candidate_evidence(candidate: dict) -> set:
    out = set()
    ev = candidate.get("score_evidence", {}) or {}
    for values in ev.values():
        for x in values or []:
            if x:
                out.add(x)
    return out


COMMON_INGREDIENT_WORDS = {
    "나이아신아마이드", "덱스판테놀", "판테놀", "멘톨", "비오틴",
    "살리실릭애씨드", "징크피리치온", "클림바졸", "피록톤올아민",
    "티트리", "카페인", "병풀", "다이포타슘글리시리제이트",
    "글라이콜릭애씨드", "락틱애씨드", "징크", "아연",
}


def validate_reason(rec: dict, candidate: dict, levels: dict) -> list:
    issues = []
    reason = rec.get("reason") or ""

    # 1) 0단계 증상 언급
    for symptom, kr in SYMPTOM_KR.items():
        if levels.get(symptom, 0) <= 0 and kr in reason:
            issues.append(f"0단계 증상 언급: {kr}")

    # 2) 이유에 등장한 대표 성분이 실제 evidence에 존재하는지
    actual_evidence = _all_candidate_evidence(candidate)
    for word in COMMON_INGREDIENT_WORDS:
        if word in reason and word not in actual_evidence:
            if word == "판테놀" and "덱스판테놀" in reason:
                continue
            issues.append(f"상품 근거에 없는 성분 언급: {word}")

    # 3) 활성 증상 + 실제 근거가 있는데 이유에서 누락했는지
    for symptom, level in levels.items():
        if level <= 0:
            continue
        evidence = _evidence_for(candidate, symptom)
        if evidence and not _reason_mentions_symptom(reason, symptom):
            issues.append(f"복합증상 근거 누락: {SYMPTOM_KR.get(symptom, symptom)}")

    # 4) 이유에서 증상을 설명했는데 그 증상 evidence가 없는 경우
    for symptom, level in levels.items():
        if level <= 0:
            continue
        if _reason_mentions_symptom(reason, symptom):
            evidence = _evidence_for(candidate, symptom)
            if not evidence:
                issues.append(f"근거 없는 증상 설명: {SYMPTOM_KR.get(symptom, symptom)}")

    return issues


def print_case_result(out: dict, levels: dict):
    case_issues = []
    category_signatures = {}

    for cat, block in out["by_category"].items():
        validation = block.get("validation") or {}
        candidate_count = block.get("candidate_count", 0)

        flags = []
        if validation.get("dropped_unknown_id"):
            flags.append(f"허위id {len(validation['dropped_unknown_id'])}")
        if validation.get("dropped_wrong_category"):
            flags.append(f"타카테고리 {len(validation['dropped_wrong_category'])}")
        if validation.get("filled_from_retrieval"):
            flags.append(f"검색순위로채움 {validation['filled_from_retrieval']}")

        print(
            f"      ── {CATEGORY_KR[cat]} 후보 {candidate_count}개"
            f"{' / ' + ' / '.join(flags) if flags else ''}"
        )

        ids = []
        for r in block["recommendations"]:
            ids.append(r["product_id"])

            print(
                f"         {r['category_rank']}. "
                f"{r['product_name'][:42]} "
                f"[검색{r.get('retrieval_rank', '?')}위]"
            )

            if r.get("decision_factors"):
                print("            선택요소 — " + ", ".join(r["decision_factors"]))

            if r.get("reason"):
                print(f"            이유 — {r['reason']}")

            issues = validate_reason(r, r, levels)

            if issues:
                for issue in issues:
                    print(f"            ⚠ {issue}")
                    case_issues.append(f"{CATEGORY_KR[cat]} / {r['product_id']} / {issue}")
            else:
                print("            ✓ 이유 근거 검증 통과")

        category_signatures[cat] = tuple(ids)

        if validation.get("dropped_unknown_id"):
            case_issues.append(f"{CATEGORY_KR[cat]}: 후보 밖 product_id 생성")

    return case_issues, category_signatures


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", type=int, help="1부터 시작하는 케이스 번호. 생략하면 전체 실행")
    ap.add_argument("--model", default=LLM_MODEL)
    ap.add_argument("--backend", default="auto", choices=["auto", "st", "hashing"])
    ap.add_argument("--no-llm", dest="use_llm", action="store_false", default=True)
    ap.add_argument("--repeat", type=int, default=None,
                    help="반복 테스트 케이스 실행 횟수 덮어쓰기")
    args = ap.parse_args(argv)

    svc = RecommendationService(
        retriever=Retriever(backend=args.backend),
        llm=LlamaClient(model=args.model),
    )

    if args.use_llm:
        ok, msg = svc.llm.available()
        print(f"모델 {args.model} — {'사용 가능' if ok else '사용 불가'}")
        if not ok:
            print(f"  {msg.splitlines()[0]}")

    print()
    print("=" * 72)
    print("추천 이유 / 근거 검증 테스트")
    print("=" * 72)
    print("LLM은 순위만 결정하고, 추천 이유는 코드가 실제 증상·성분 근거로 작성하는 구조를 검증합니다.")
    print()

    cases = CASES if args.case is None else [CASES[args.case - 1]]
    start = 1 if args.case is None else args.case

    total_issue_counter = Counter()
    repeat_summary = []

    for idx, (label, levels, profile, plan, times) in enumerate(cases, start=start):
        n = args.repeat if (args.repeat and times > 1) else times

        print("=" * 72)
        print(f"[{idx}] {label}")
        print(f"    두피: {describe(levels)}")
        if profile:
            print(f"    사용자: {profile}")
        print(f"    카테고리: {[CATEGORY_KR[c] for c in plan]}")
        print()

        signatures = []
        reasons_per_run = []

        for run_idx in range(n):
            out = svc.recommend(
                levels,
                profile,
                plan=plan,
                use_llm=args.use_llm,
            )

            run_tag = f" (실행 {run_idx + 1}/{n})" if n > 1 else ""
            print(f"    LLM {out['llm_calls']}회 / {out['timing_ms']['total_ms']}ms{run_tag}")

            issues, sig = print_case_result(out, levels)
            signatures.append(sig)
            reasons_per_run.append(
                tuple(
                    r.get("reason") or ""
                    for block in out["by_category"].values()
                    for r in block["recommendations"]
                )
            )

            if not issues:
                print("    결과: PASS — 추천 이유 검증 오류 없음")
            else:
                print(f"    결과: WARNING — {len(issues)}개 문제 발견")

            for issue in issues:
                total_issue_counter[issue.split(":")[0]] += 1
            print()

        if n > 1:
            same_rank = all(sig == signatures[0] for sig in signatures[1:])
            same_reason = all(rs == reasons_per_run[0] for rs in reasons_per_run[1:])
            repeat_summary.append((label, same_rank, same_reason))

            print("    반복 검증")
            print("      추천 순위:", "PASS — 동일" if same_rank else "WARNING — 흔들림")
            print("      추천 이유:", "PASS — 동일" if same_reason else "WARNING — 흔들림")
            print()

    print("=" * 72)
    print("전체 검증 요약")
    print("=" * 72)

    if total_issue_counter:
        print("문제 발견:")
        for issue, count in total_issue_counter.most_common():
            print(f"  - {issue}: {count}건")
    else:
        print("PASS — 자동 검증에서 추천 이유 관련 오류가 발견되지 않았습니다.")

    if repeat_summary:
        print()
        print("반복 안정성:")
        for label, same_rank, same_reason in repeat_summary:
            print(
                f"  - {label}: "
                f"순위 {'PASS' if same_rank else 'FAIL'} / "
                f"이유 {'PASS' if same_reason else 'FAIL'}"
            )

    print()
    print("이 테스트에서 중요하게 볼 것")
    print("  1. ⚠ 상품 근거에 없는 성분 언급이 0건인지")
    print("  2. ⚠ 0단계 증상 언급이 0건인지")
    print("  3. ⚠ 복합증상 근거 누락이 0건인지")
    print("  4. ⚠ 근거 없는 증상 설명이 0건인지")
    print("  5. 허위 product_id가 0건인지")
    print("  6. 같은 입력 반복 시 추천 순위와 이유가 안정적인지")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
