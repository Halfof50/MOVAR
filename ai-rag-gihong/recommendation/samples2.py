"""
경계 조건 점검용 샘플

samples.py 와 목적이 다르다.
    samples.py   같은 증상 + 다른 개인정보 → 개인화가 작동하는지
    samples2.py  증상 쪽 경계 조건 → 문장과 선택이 깨지는 지점을 찾는다

samples.py 가 다루지 않는 구간만 넣었다.
    증상이 하나뿐일 때          samples.py 는 전부 2개 이상이거나 0개다
    전부 1단계 (경미) 일 때      약한 증상에 과한 추천을 하는지
    두 증상이 같은 레벨일 때      '가장 심한 증상' 을 무엇으로 고르는지
    같은 레벨 1 과 3 비교        레벨이 선택을 바꾸는지
    후보 풀이 작은 카테고리        스케일러 17개, 트리트먼트 20개
    후보가 뽑을 개수보다 적을 때    검색 순위로 채우는 경로
    같은 입력 반복               출력이 흔들리는지 (노이즈와 개인화 구별)

이유 문장 검사는 compare_models 의 함수를 그대로 쓴다. 기준을 두 군데 두지 않는다.

    python -m recommendation.samples2                  전부
    python -m recommendation.samples2 --case 3         3번만
    python -m recommendation.samples2 --repeat 3       반복 케이스를 3회씩
    python -m recommendation.samples2 --no-llm         검색 결과만
"""

import argparse
from collections import Counter

from recommendation.compare_models import (
    META_WORDS, mentioned_ingredients, other_names,
)
from recommendation.config import CATEGORY_KR, LLM_MODEL, SYMPTOM_KR
from recommendation.llm.llama_client import LlamaClient
from recommendation.retrieval.retriever import Retriever
from recommendation.service.recommendation_service import RecommendationService

# (설명, 증상, 프로필, 카테고리 지정, 반복 횟수)
CASES = [
    # ── 증상이 하나뿐일 때 ──
    ("탈모만 3단계", {"hair_loss": 3}, {}, None, 1),
    ("비듬만 2단계", {"dandruff": 2}, {}, None, 1),
    ("미세각질만 1단계", {"micro_keratin": 1}, {}, None, 1),

    # ── 같은 증상, 레벨만 다름 ──
    ("탈모 1단계", {"hair_loss": 1}, {}, ["shampoo"], 1),
    ("탈모 3단계", {"hair_loss": 3}, {}, ["shampoo"], 1),

    # ── 전부 경미 ──
    ("6개 증상 전부 1단계",
     {"micro_keratin": 1, "excess_sebum": 1, "follicular_erythema": 1,
      "follicular_pustule": 1, "dandruff": 1, "hair_loss": 1}, {}, None, 1),

    # ── 동률 ──
    ("피지2 비듬2 (동률)", {"excess_sebum": 2, "dandruff": 2}, {}, ["shampoo"], 1),

    # ── 후보 풀이 작은 카테고리 ──
    ("스케일러만 지정 (전체 17개)", {"micro_keratin": 3}, {}, ["scaler"], 1),
    ("트리트먼트만 지정 (전체 20개)",
     {"follicular_erythema": 2}, {}, ["treatment"], 1),

    # ── 후보가 뽑을 개수보다 적을 때 ──
    ("1만원 상한 — 후보 부족 예상",
     {"hair_loss": 2}, {"max_price": 10000}, ["tonic"], 1),

    # ── 같은 입력 반복 ──
    ("반복 — 같은 입력 (노이즈 확인)",
     {"dandruff": 1, "hair_loss": 2}, {}, ["shampoo"], 3),
]


def describe(sym):
    on = [f"{SYMPTOM_KR[k]} {v}" for k, v in sym.items() if v]
    return ", ".join(on) or "전 증상 0단계"


def flags(rec, candidates):
    """이유 문장에서 규칙 위반을 찾는다. 기준은 compare_models 와 같다."""
    t = rec.get("reason") or ""
    out = []
    ing = mentioned_ingredients(t)
    if ing:
        actual = set(rec.get("active_ingredients") or [])
        fake = sorted(ing - actual)
        out.append(f"성분명 {', '.join(sorted(ing))}"
                   + (f" / 그중 제품에 없음: {', '.join(fake)}" if fake else ""))
    meta = [w for w in META_WORDS if w in t]
    if meta:
        out.append(f"메타 {', '.join(meta)}")
    on = other_names(rec, candidates)
    if on:
        out.append(f"남의 상품명 {', '.join(n[:20] for n in on)}")
    for mark in ["□□", "△△", "◇◇"]:
        if mark in t:
            out.append(f"플레이스홀더 {mark}")
    if "가장" in t and rec.get("category_rank", 1) > 1:
        out.append("2·3순위인데 '가장'")
    return out


def run_one(svc, sym, profile, plan, use_llm):
    return svc.recommend(sym, profile, plan=plan, use_llm=use_llm)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", type=int, help="1부터 시작하는 번호")
    ap.add_argument("--model", default=LLM_MODEL)
    ap.add_argument("--no-llm", dest="use_llm", action="store_false", default=True)
    ap.add_argument("--backend", default="auto", choices=["auto", "st", "hashing"])
    ap.add_argument("--repeat", type=int, default=None,
                    help="반복 케이스의 실행 횟수를 덮어쓴다")
    args = ap.parse_args(argv)

    svc = RecommendationService(retriever=Retriever(backend=args.backend),
                                llm=LlamaClient(model=args.model))
    if args.use_llm:
        ok, msg = svc.llm.available()
        print(f"모델 {args.model} — {'사용 가능' if ok else '사용 불가'}")
        if not ok:
            print(f"  {msg.splitlines()[0]}")
    print()

    cases = CASES if args.case is None else [CASES[args.case - 1]]
    start = 1 if args.case is None else args.case

    total_flags = Counter()
    repeat_report = []

    for i, (label, sym, profile, plan, times) in enumerate(cases, start=start):
        n = args.repeat if (args.repeat and times > 1) else times
        print("=" * 72)
        print(f"[{i}] {label}")
        print(f"    두피: {describe(sym)}")
        if profile:
            print(f"    사용자: {profile}")

        runs = []
        for t in range(n):
            out = run_one(svc, sym, profile, plan, args.use_llm)
            runs.append(out)
            tag = f"  (실행 {t + 1}/{n})" if n > 1 else ""
            print(f"    카테고리 {[CATEGORY_KR[c] for c in out['categories']]}"
                  f"  LLM {out['llm_calls']}회  {out['timing_ms']['total_ms']}ms{tag}")
            if out["note"]:
                print(f"    참고: {out['note'][:100]}")

            for cat, block in out["by_category"].items():
                v = block["validation"]
                bad = []
                if v.get("dropped_unknown_id"):
                    bad.append(f"허위id {len(v['dropped_unknown_id'])}")
                if v.get("dropped_wrong_category"):
                    bad.append(f"타카테고리 {len(v['dropped_wrong_category'])}")
                if v.get("filled_from_retrieval"):
                    bad.append(f"검색순위로채움 {v['filled_from_retrieval']}")
                if v.get("picked_by_gentleness"):
                    bad.append(f"순한정도로선택 {v['picked_by_gentleness']}")
                print(f"      ── {CATEGORY_KR[cat]} 후보 {block['candidate_count']}개"
                      f"{' / ' + ', '.join(bad) if bad else ''}")

                for r in block["recommendations"]:
                    print(f"         {r['category_rank']}. {r['product_name'][:36]}"
                          f"  [검색{r['retrieval_rank']}위]")
                    if r["reason"]:
                        print(f"            {r['reason']}")
                    f = flags(r, block["recommendations"])
                    for x in f:
                        total_flags[x.split()[0]] += 1
                        print(f"            ⚠ {x}")
                    if r.get("evidence_note"):
                        print(f"            근거 — {r['evidence_note'][:90]}")
            print()

        if n > 1:
            sigs = ["|".join(f"{c}:{','.join(str(x['product_id']) for x in b['recommendations'])}"
                             for c, b in o["by_category"].items()) for o in runs]
            same = len(set(sigs)) == 1
            repeat_report.append((label, same, sigs))
            print(f"    반복 결과 — 추천 상품이 {'매번 동일' if same else '흔들림'}")
            for k, s in enumerate(sigs, start=1):
                print(f"      {k}회차 {s}")
            reasons = [tuple(x["reason"] for b in o["by_category"].values()
                             for x in b["recommendations"]) for o in runs]
            print(f"    이유 문장은 {'매번 동일' if len(set(reasons)) == 1 else '다름'}")
            print()

    print("=" * 72)
    print("규칙 위반 집계")
    if total_flags:
        for k, v in total_flags.most_common():
            print(f"  {k} {v}건")
    else:
        print("  없음")

    if repeat_report:
        print("\n반복 케이스")
        for label, same, _ in repeat_report:
            print(f"  {label} — {'동일' if same else '흔들림'}")
        print("  흔들리면 samples.py 1~3번의 토닉 차이는 개인화가 아니라 노이즈다")

    print("\n이 파일로 보는 것")
    print("  증상이 하나뿐일 때 문장이 어색해지지 않는지 (1~3번)")
    print("  레벨 1과 3에서 추천이 달라지는지 (4·5번)")
    print("  전부 1단계일 때 과한 제품을 고르지 않는지 (6번)")
    print("  동률일 때 '가장 심한 증상' 을 무엇으로 삼는지 (7번)")
    print("  후보 풀이 작아도 비교가 되는지 (8·9번)")
    print("  후보가 모자랄 때 검색순위로 채우는지 (10번)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
