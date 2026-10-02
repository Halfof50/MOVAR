"""
로컬 모델 비교

같은 입력을 여러 모델에 넣고 세 가지를 잰다.
'JSON 형식이 맞는가' 같은 건 통과해도 추천이 쓸모없을 수 있어서 보조 지표로만 둔다.

  1. 개인정보 민감도
     증상이 같고 개인정보만 다른 사용자끼리 추천이 얼마나 겹치는지.
     100% 면 개인정보가 결과를 전혀 바꾸지 못한다는 뜻이다.

  2. 쏠림
     전체 호출에서 상품별 추천 횟수. 최다 상품이 몇 퍼센트를 가져가는지,
     서로 다른 상품이 몇 종류나 나왔는지.

  3. 설명 정확도
     이유 문장에서 성분 이름과 증상 이름을 뽑아 실제 데이터와 대조한다.
       성분언급 성분 이름을 이유에 적었다. 규칙으로 금지한 항목이다
       메타언급 가격·평점·리뷰 수·상품명을 적었다. 역시 금지한 항목이다
       미포함   그 상품에 없는 성분을 적었다
       짝오류   그 증상의 근거 성분이 아닌 것을 그 증상의 근거로 적었다
       레벨0    0단계인 증상을 이유로 들었다
       거짓리뷰 리뷰가 1천 건 미만인데 '리뷰 수가 많다' 고 적었다
       남의이름 같은 호출의 다른 후보 상품명을 적었다

알레르기는 재지 않는다. 추천 경로에서 빼두었고 별도 모듈로 분리할 예정이다.

    ollama pull exaone3.5:7.8b
    ollama pull qwen2.5:14b

    python -m recommendation.compare_models --temperature 0
    python -m recommendation.compare_models --models llama3.1:8b-instruct-q4_K_M qwen2.5:14b
    python -m recommendation.compare_models --detail      # 위반 사례를 하나씩 출력
"""

import argparse
import itertools
import time
from collections import Counter

from recommendation.config import (
    CANDIDATES_PER_CATEGORY, LLM_MODEL, PICK_PER_CATEGORY, SYMPTOMS, SYMPTOM_KR,
)
from recommendation.llm.llama_client import LlamaClient
from recommendation.llm.output_parser import parse_and_validate
from recommendation.llm.recommendation_prompt import build_category_prompt
from recommendation.preprocessing.ingredient_normalizer import ALIASES
from recommendation.retrieval.retriever import Retriever

DEFAULT_MODELS = [
    "llama3.1:8b-instruct-q4_K_M",
    "exaone3.5:7.8b",
    "qwen2.5:14b",
]

# ── 1. 개인정보 민감도용 ────────────────────────────────
# 증상은 같고 개인정보만 다르다. 결과가 달라져야 개인화가 작동하는 것이다.
SENSITIVITY_GROUPS = [
    ("비듬1 탈모2", {"dandruff": 1, "hair_loss": 2}, [
        ("미등록",      {}),
        ("10대 매일",   {"age_group": "10대", "wash_frequency": "하루 1회"}),
        ("30대 매일",   {"age_group": "30대", "wash_frequency": "하루 1회"}),
        ("50대 이틀에한번", {"age_group": "50대 이상", "wash_frequency": "2일에 1회"}),
        ("2만원 이하",  {"age_group": "20대", "max_price": 20000}),
    ]),
    ("각질3 피지2", {"micro_keratin": 3, "excess_sebum": 2}, [
        ("미등록",      {}),
        ("40대 하루2회", {"age_group": "40대", "wash_frequency": "하루 2회"}),
        ("3만원 이하",  {"age_group": "30대", "max_price": 30000}),
    ]),
]

# ── 2. 쏠림용 ───────────────────────────────────────────
# 증상만 바꿔가며 돌린다. 매번 같은 상품이 나오면 쏠림이다.
COVERAGE_CASES = [
    {"dandruff": 3},
    {"hair_loss": 3},
    {"micro_keratin": 3},
    {"excess_sebum": 3},
    {"follicular_erythema": 2, "follicular_pustule": 2},
    {},
]

# 이유 문장에서 성분 이름을 찾기 위한 표기 목록
INGREDIENT_TERMS = {canon: [canon] + names for canon, names in ALIASES.items()}


def mentioned_ingredients(text: str) -> set:
    """이유 문장에 등장한 대표 성분명"""
    found = set()
    for canon, terms in INGREDIENT_TERMS.items():
        if any(t in text for t in terms):
            found.add(canon)
    return found


def mentioned_symptoms(text: str) -> set:
    return {s for s in SYMPTOMS if SYMPTOM_KR[s] in text}


# 이유에 쓰면 안 되는 메타 정보 표현
META_WORDS = ["리뷰", "평점", "가격", "저렴", "비싸", "경제적", "원대", "후기"]


def other_names(rec: dict, candidates: list) -> list:
    """이유 문장에 들어간 '다른 후보' 의 상품명"""
    text = rec.get("reason") or ""
    mine = rec.get("product_name") or ""
    hits = []
    for c in candidates:
        n = (c.get("name_clean") or c.get("name") or "").strip()
        if len(n) >= 8 and n in text and n != mine:
            hits.append(n)
    return hits


def audit_reason(rec: dict, levels: dict) -> dict:
    """이유 문장 한 건을 검사한다."""
    text = rec.get("reason") or ""
    said_ing = mentioned_ingredients(text)
    said_sym = mentioned_symptoms(text)
    actives = set(rec.get("active_ingredients") or [])
    evidence = rec.get("score_evidence") or {}

    # 그 상품에 아예 없는 성분을 적었다
    not_in_product = said_ing - actives

    # 언급한 증상들의 근거 성분 합집합에 없는 성분을 적었다
    allowed = set()
    for s in said_sym:
        allowed |= set(evidence.get(s) or [])
    wrong_pair = set()
    if said_sym:
        wrong_pair = (said_ing & actives) - allowed

    # 0단계 증상을 이유로 들었다
    zero_used = {SYMPTOM_KR[s] for s in said_sym if levels.get(s, 0) == 0}

    # 가격·리뷰·평점은 화면에 숫자로 나가므로 이유에 적으면 안 된다.
    meta = [w for w in META_WORDS if w in text]

    # '리뷰 수가 많다' 고 했는데 실제로 1천 건 미만인 경우
    false_review = False
    if "리뷰" in text and any(k in text for k in ["많", "다수", "풍부"]):
        false_review = (rec.get("reviews") or 0) < 1000

    return {
        # 성분 이름을 적는 것 자체가 규칙 위반이다. 근거 성분은 코드가 따로 표시한다.
        "named": sorted(said_ing),
        "meta": meta,
        "false_review": false_review,
        "not_in_product": sorted(not_in_product),
        "wrong_pair": sorted(wrong_pair),
        "zero_used": sorted(zero_used),
    }


def one_call(client, retriever, symptoms, profile, category, pick, top_k,
             temperature, acc, label):
    """한 번 호출하고 결과를 acc 에 쌓는다."""
    res = retriever.retrieve_category(symptoms, category, profile, top_k=top_k)
    cands = res["candidates"]
    if not cands:
        return []

    prompt = build_category_prompt(res["levels"], profile, cands, category, pick=pick)

    t0 = time.time()
    try:
        out = client.generate_json(prompt, temperature=temperature, retries=0)
        acc["json_ok"] += 1
    except Exception as e:
        acc["errors"].append(f"{label}: {type(e).__name__}: {e}")
        out = {}
    acc["latency"].append(time.time() - t0)
    acc["calls"] += 1

    recs, log = parse_and_validate(out or {}, cands, res["levels"],
                                   pick=pick, require_category=category)
    acc["fake_id"] += len(log["dropped_unknown_id"]) + len(log["dropped_wrong_category"])

    picked = [r for r in recs if r["picked_by"] == "llm"]
    acc["picked_total"] += len(picked)

    # 설명 정확도
    for r in picked:
        a = audit_reason(r, res["levels"])
        if a["named"]:
            acc["named"] += 1
            acc["detail"].append(f"[성분언급] {label} / {r['product_name'][:24]} / "
                                 f"{', '.join(a['named'])}")
        if a["meta"]:
            acc["meta"] += 1
            acc["detail"].append(f"[메타언급] {label} / {r['product_name'][:24]} / "
                                 f"{', '.join(a['meta'])}")
        if a["false_review"]:
            acc["false_review"] += 1
            acc["detail"].append(f"[거짓리뷰] {label} / {r['product_name'][:24]} / "
                                 f"실제 {r.get('reviews', 0):,}건인데 많다고 적음")
        on = other_names(r, cands)
        if on:
            acc["other_name"] += 1
            acc["detail"].append(f"[남의이름] {label} / {r['product_name'][:24]} / "
                                 f"이유에 등장: {', '.join(n[:22] for n in on)}")
        if a["not_in_product"]:
            acc["not_in_product"] += 1
            acc["detail"].append(f"[미포함] {label} / {r['product_name'][:24]} / "
                                 f"{', '.join(a['not_in_product'])}")
        if a["wrong_pair"]:
            acc["wrong_pair"] += 1
            acc["detail"].append(f"[짝오류] {label} / {r['product_name'][:24]} / "
                                 f"{', '.join(a['wrong_pair'])}")
        if a["zero_used"]:
            acc["zero_used"] += 1
            acc["detail"].append(f"[레벨0]  {label} / {r['product_name'][:24]} / "
                                 f"{', '.join(a['zero_used'])}")

    acc["appear"].update(r["product_id"] for r in picked)
    return [r["product_id"] for r in picked]


def new_acc():
    return {"calls": 0, "json_ok": 0, "fake_id": 0, "picked_total": 0,
            "named": 0, "meta": 0, "false_review": 0, "other_name": 0,
            "not_in_product": 0, "wrong_pair": 0, "zero_used": 0,
            "appear": Counter(), "latency": [],
            "errors": [], "detail": []}


def jaccard(a, b):
    a, b = set(a), set(b)
    u = a | b
    return len(a & b) / len(u) if u else 1.0


def run_model(client, retriever, args):
    acc = new_acc()
    overlaps = []

    # 1. 개인정보 민감도
    for gname, symptoms, profiles in SENSITIVITY_GROUPS:
        picks = []
        for pname, profile in profiles:
            ids = one_call(client, retriever, symptoms, profile, args.category,
                           args.pick, args.top_k, args.temperature, acc,
                           f"{gname}/{pname}")
            picks.append(ids)
        for a, b in itertools.combinations([p for p in picks if p], 2):
            overlaps.append(jaccard(a, b))

    # 2. 쏠림
    for sym in COVERAGE_CASES:
        label = ", ".join(f"{SYMPTOM_KR[k]}{v}" for k, v in sym.items()) or "전부0"
        one_call(client, retriever, sym, {}, args.category,
                 args.pick, args.top_k, args.temperature, acc, label)

    total_picks = sum(acc["appear"].values())
    top_share = (acc["appear"].most_common(1)[0][1] / total_picks) if total_picks else 0
    n = max(acc["picked_total"], 1)

    return {
        "overlap": sum(overlaps) / len(overlaps) if overlaps else 0,
        "top_share": top_share,
        "distinct": len(acc["appear"]),
        "named": acc["named"] / n,
        "meta": acc["meta"] / n,
        "false_review": acc["false_review"],
        "other_name": acc["other_name"],
        "not_in_product": acc["not_in_product"] / n,
        "wrong_pair": acc["wrong_pair"] / n,
        "zero_used": acc["zero_used"] / n,
        "json_fail": acc["calls"] - acc["json_ok"],
        "fake_id": acc["fake_id"],
        "latency": sum(acc["latency"]) / len(acc["latency"]) if acc["latency"] else 0,
        "detail": acc["detail"],
        "errors": acc["errors"],
        "top_products": acc["appear"].most_common(5),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    ap.add_argument("--category", default="shampoo")
    ap.add_argument("--pick", type=int, default=PICK_PER_CATEGORY)
    ap.add_argument("--top-k", type=int, default=CANDIDATES_PER_CATEGORY)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--backend", default="auto", choices=["auto", "st", "hashing"])
    ap.add_argument("--detail", action="store_true", help="위반 사례를 하나씩 출력")
    args = ap.parse_args(argv)

    retriever = Retriever(backend=args.backend)
    n_calls = sum(len(p) for _, _, p in SENSITIVITY_GROUPS) + len(COVERAGE_CASES)
    print(f"카테고리 {args.category} / 후보 {args.top_k}개 중 {args.pick}개 선택"
          f" / temperature {args.temperature}")
    print(f"모델당 호출 {n_calls}회 "
          f"(개인정보 비교 {n_calls - len(COVERAGE_CASES)}회 + 쏠림 {len(COVERAGE_CASES)}회)\n")

    header = (f"{'모델':26s} {'겹침':>5s} {'최다':>5s} {'종류':>5s} "
              f"{'성분':>5s} {'메타':>5s} {'거짓리뷰':>8s} {'남의이름':>8s} "
              f"{'짝오류':>6s} {'레벨0':>6s} {'초':>5s}")
    print(header)
    print("-" * len(header))

    results = {}
    for name in args.models:
        client = LlamaClient(model=name)
        ok, msg = client.available()
        if not ok:
            print(f"{name:28s}  건너뜀 — {msg.splitlines()[0].split('(')[0].strip()}")
            continue
        m = run_model(client, retriever, args)
        results[name] = m
        print(f"{name:26s} {m['overlap']:4.0%} {m['top_share']:5.0%} "
              f"{m['distinct']:4d}종 {m['named']:5.0%} {m['meta']:5.0%} "
              f"{m['false_review']:7d}건 {m['other_name']:7d}건 "
              f"{m['wrong_pair']:6.0%} {m['zero_used']:6.0%} {m['latency']:4.1f}s")

    if not results:
        print("\n사용 가능한 모델이 없습니다. 'ollama serve' 와 'ollama pull' 을 확인하십시오.")
        return 1

    print("\n읽는 법")
    print("  겹침   낮을수록 좋다. 증상이 같고 개인정보만 다른 사용자끼리의 추천 겹침률.")
    print("         100% 면 개인정보가 결과를 전혀 바꾸지 못한다는 뜻")
    print("  최다   낮을수록 좋다. 한 상품이 전체 추천에서 차지하는 비율")
    print("  종류   높을수록 좋다. 서로 다른 상품이 몇 종류나 추천됐는지")
    print("  성분   이유에 성분 이름을 적은 비율. 금지 항목이므로 0% 가 목표다")
    print("  메타   이유에 가격·평점·리뷰 수를 적은 비율. 역시 0% 가 목표다")
    print("  거짓리뷰 리뷰 1천 건 미만인 상품에 '리뷰가 많다' 고 적은 횟수")
    print("  남의이름 같은 호출의 다른 후보 상품명을 이유에 적은 횟수")
    print("  짝오류 그 증상의 근거가 아닌 성분을 그 증상의 근거로 적은 비율")
    print("  레벨0  0단계 증상을 이유로 든 비율")

    for name, m in results.items():
        print(f"\n── {name} ──")
        print("  자주 뽑힌 상품:", ", ".join(
            f"{pid}×{c}" for pid, c in m["top_products"]) or "없음")
        if m["json_fail"] or m["fake_id"]:
            print(f"  JSON 실패 {m['json_fail']}회, 후보 밖 id {m['fake_id']}건")
        if m["errors"]:
            print("  오류:", m["errors"][0])
        if args.detail:
            for d in m["detail"][:20]:
                print("   ", d)
            if len(m["detail"]) > 20:
                print(f"    ... 외 {len(m['detail']) - 20}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
