"""
추천 파이프라인.

RAG가 카테고리별 후보를 검색하고,
LLM은 후보 전체에 각각 0~100 적합도 점수 + decision_factors만 부여한다.
Python이 점수순으로 정렬해 Top K를 선택하고 실제 product_id/상품명/추천 이유를 붙인다.

따라서 LLM은 product_id를 생성하지 않는다.
"""

import time

from recommendation.config import (
    CANDIDATES_PER_CATEGORY, CATEGORY_KR, CATEGORY_ORDER, FALLBACK_PLAN_RULES,
    MAX_CATEGORIES, PICK_PER_CATEGORY, SYMPTOM_KR,
)
from recommendation.llm.llama_client import LlamaClient
from recommendation.llm.output_parser import parse_score_evaluations, pick_gentle
from recommendation.llm.recommendation_prompt import build_category_prompt
from recommendation.retrieval.query_builder import normalize_levels, ranked_symptoms
from recommendation.retrieval.retriever import Retriever


def resolve_categories(plan=None, report=None, levels=None) -> list:
    raw = plan
    if raw is None and report:
        raw = (report.get("product_plan") or {}).get("combo")

    cats = []
    for item in (raw or []):
        c = item.get("category") if isinstance(item, dict) else item
        if c in CATEGORY_KR and c not in cats:
            cats.append(c)

    if not cats:
        cats = ["shampoo"]
        lv = levels or {}
        for cat, conds in FALLBACK_PLAN_RULES:
            if any(lv.get(sym, 0) >= need for sym, need in conds):
                cats.append(cat)

    cats = [c for c in CATEGORY_ORDER if c in cats]
    return cats[:MAX_CATEGORIES]


class RecommendationService:

    def __init__(self, retriever=None, llm=None, backend="auto"):
        self.retriever = retriever or Retriever(backend=backend)
        self.llm = llm if llm is not None else LlamaClient()

    def recommend(self, scalp_analysis: dict, user_profile: dict = None,
                  plan=None, report=None,
                  pick: int = PICK_PER_CATEGORY,
                  top_k: int = CANDIDATES_PER_CATEGORY,
                  include_full_ingredients: bool = False,
                  shuffle: bool = None,
                  use_llm: bool = True):
        t0 = time.time()
        profile = user_profile or {}
        levels = normalize_levels(scalp_analysis)
        categories = resolve_categories(plan, report, levels)
        all_zero = not any(levels.values())

        llm_ok, llm_msg = (
            self.llm.available() if (use_llm and not all_zero)
            else (False, "LLM 사용이 꺼져 있습니다.")
        )

        by_category, flat, notes = {}, [], []

        for cat in categories:
            t1 = time.time()
            res = self.retriever.retrieve_category(levels, cat, profile, top_k=top_k)
            cands = res["candidates"]
            actual_pick = min(pick, len(cands))

            if not cands:
                by_category[cat] = {
                    "query": res["query"], "candidate_count": 0,
                    "recommendations": [], "validation": {},
                    "note": f"{CATEGORY_KR[cat]} 후보가 없습니다.", "timing_ms": {},
                }
                notes.append(by_category[cat]["note"])
                continue

            if all_zero:
                recs, log = pick_gentle(cands, pick=actual_pick)
                for r in recs:
                    r["category_rank"] = r["rank"]
                flat.extend(recs)

                note = "증상이 모두 0단계여서 순한 정도 기준으로 선택했습니다."
                if note not in notes:
                    notes.append(note)

                by_category[cat] = {
                    "query": res["query"],
                    "candidate_count": len(cands),
                    "candidate_ids": [c["product_id"] for c in cands],
                    "recommendations": recs,
                    "validation": log,
                    "prompt_chars": 0,
                    "note": note,
                    "timing_ms": {
                        "retrieve_ms": int((time.time() - t1) * 1000),
                        "llm_ms": 0,
                    },
                }
                continue

            prompt = build_category_prompt(
                levels, profile, cands, cat, pick=actual_pick,
                include_full_ingredients=include_full_ingredients,
                shuffle=shuffle,
            )

            llm_output, note = {}, None
            t2 = time.time()

            if llm_ok:
                try:
                    llm_output = self.llm.generate_json(prompt) or {}
                except Exception as e:
                    note = (
                        f"{CATEGORY_KR[cat]}: LLM 평가 실패로 검색 후보 순서를 사용했습니다. "
                        f"{type(e).__name__}: {e}"
                    )
            else:
                note = f"LLM을 사용할 수 없어 검색 후보 순서를 사용했습니다. {llm_msg.splitlines()[0]}"

            llm_ms = int((time.time() - t2) * 1000)

            # LLM은 candidate_no + score만 출력한다.
            # 실제 product_id 매핑과 Top K 정렬은 이 함수 안에서 Python이 한다.
            recs, log = parse_score_evaluations(
                llm_output,
                cands,
                levels=levels,
                profile=profile,
                pick=actual_pick,
                require_category=cat,
            )

            for r in recs:
                r["category_rank"] = r["rank"]

            flat.extend(recs)
            if note and note not in notes:
                notes.append(note)

            by_category[cat] = {
                "query": res["query"],
                "candidate_count": len(cands),
                "candidate_ids": [c["product_id"] for c in cands],
                "recommendations": recs,
                "validation": log,
                "prompt_chars": len(prompt),
                "note": note,
                "timing_ms": {
                    "retrieve_ms": int((t2 - t1) * 1000),
                    "llm_ms": llm_ms,
                },
            }

        for i, r in enumerate(flat, start=1):
            r["rank"] = i

        return {
            "levels": levels,
            "priority": ranked_symptoms(levels),
            "categories": categories,
            "by_category": by_category,
            "recommendations": flat,
            "llm_available": llm_ok,
            "llm_calls": 0 if all_zero else sum(
                1 for b in by_category.values() if b["candidate_count"]
            ),
            "all_zero": all_zero,
            "note": "; ".join(notes) or None,
            "timing_ms": {"total_ms": int((time.time() - t0) * 1000)},
        }


def print_result(result: dict):
    print("증상 :", ", ".join(
        f"{SYMPTOM_KR[k]} {v}" for k, v in result["levels"].items() if v
    ))
    print("우선순위:", [SYMPTOM_KR[s] for s in result["priority"]])
    print("추천 카테고리:", [CATEGORY_KR[c] for c in result["categories"]],
          f"→ LLM 호출 {result['llm_calls']}회")
    print("총 소요:", result["timing_ms"]["total_ms"], "ms")
    if result["note"]:
        print("참고 :", result["note"])
    print()

    for cat, block in result["by_category"].items():
        print(f"── {CATEGORY_KR[cat]} (후보 {block['candidate_count']}개) ──")
        print(f"   검증 {block['validation']}")
        for r in block["recommendations"]:
            print(f"   {r['category_rank']}. {r['product_name'][:40]}")
            print(
                f"      검색순위 {r.get('retrieval_rank')} / "
                f"LLM점수 {r.get('llm_score')} / "
                f"후보번호 {r.get('candidate_no')}"
            )
            if r.get("decision_factors"):
                print("      판단요소", ", ".join(r["decision_factors"]))
            if r.get("reason"):
                print("      이유", r["reason"])
            if r.get("evidence_note"):
                print("      근거", r["evidence_note"])
        print()


if __name__ == "__main__":
    svc = RecommendationService(backend="hashing")
    result = svc.recommend(
        {"dandruff": 1, "hair_loss": 2},
        {"age_group": "30대", "wash_frequency": "하루 1회", "max_price": 60000},
        plan=["shampoo"],
    )
    print_result(result)
