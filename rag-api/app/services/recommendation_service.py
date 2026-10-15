"""MOVAR demo recommender: Retrieval Test 2 (7+15=22) + Qwen Test 5.

Only the LLM supplies scores. Python owns candidate IDs, ordering and verifiable
ingredient evidence. Legacy per-category settings are not used in this path.
"""
import time
from app.config import CATEGORY_KR, HYBRID_TOTAL_K, SYMPTOM_KR
from app.llm.qwen_client import QwenScoringClient
from app.llm.test5_prompt import build_prompt
from app.llm.evidence import evidence_note
from app.retrieval.preprocessing.gentleness import gentle_reason
from app.retrieval.query_builder import normalize_levels, ranked_symptoms
from app.retrieval.retriever import Retriever


class RecommendationService:
    def __init__(self, retriever=None, llm=None, backend="auto"):
        self.retriever = retriever if retriever is not None else Retriever(backend=backend)
        self.llm = llm if llm is not None else QwenScoringClient()

    def recommend(self, scalp_analysis: dict, user_profile: dict = None,
                  plan=None, report=None, pick: int = 3, top_k: int = HYBRID_TOTAL_K,
                  include_full_ingredients: bool = True, shuffle: bool = False,
                  use_llm: bool = True):
        started = time.perf_counter()
        levels = normalize_levels(scalp_analysis)
        profile = user_profile or {}
        # No plan -> all categories: this matches retrieval evaluation more closely.
        if plan is None and report:
            plan = (report.get("product_plan") or {}).get("combo")
        categories = None
        if plan:
            cats = [item.get("category") if isinstance(item, dict) else item for item in plan]
            categories = [cat for cat in cats if cat in CATEGORY_KR]
            if not categories:
                raise ValueError("유효하지 않은 상품 카테고리입니다.")

        found = self.retriever.retrieve_hybrid(
            levels, profile=profile, top_k=top_k, categories=categories
        )
        candidates = found["candidates"]
        if not candidates:
            return {
                "status": "empty", "levels": levels, "priority": ranked_symptoms(levels),
                "query": found["query"], "candidate_count": 0,
                "recommendations": [], "categories": [], "llm_calls": 0,
                "retrieval": {"embedding_count": 0, "ingredient_count": 0},
                "timing_ms": {"total_ms": int((time.perf_counter()-started)*1000)},
            }

        limit = min(max(1, int(pick)), len(candidates))
        all_zero = not any(levels.values())
        if all_zero:
            ranked = sorted(candidates, key=lambda c: (
                -float(c.get("gentleness") or 0), c["retrieval_rank"]
            ))[:limit]
            chosen = [(c, None, "gentleness") for c in ranked]
            calls = 0
            prompt_chars = 0
        elif not use_llm:
            return {
                "status": "retrieval_only", "levels": levels, "priority": ranked_symptoms(levels),
                "query": found["query"], "candidate_count": len(candidates),
                "candidate_ids": [c["product_id"] for c in candidates],
                "recommendations": [], "categories": [], "llm_calls": 0,
                "retrieval": {"embedding_count": found["embedding_count"],
                              "ingredient_count": found["ingredient_count"]},
                "timing_ms": {"total_ms": int((time.perf_counter()-started)*1000)},
            }
        else:
            ok, reason = self.llm.available()
            if not ok:
                raise RuntimeError(reason)
            prompt = build_prompt(levels, profile, candidates)
            scores = self.llm.score(prompt, len(candidates))
            # Same-score tie break follows fixed candidate_position, as in Test 5.
            ranked = sorted(enumerate(candidates, 1), key=lambda p: (
                -scores[f"C{p[0]:02d}"], p[0]
            ))[:limit]
            chosen = [(c, scores[f"C{i:02d}"], "llm_score") for i, c in ranked]
            calls = 1
            prompt_chars = len(prompt)

        results = []
        for rank, (c, score, picked) in enumerate(chosen, 1):
            results.append({
                "rank": rank, "product_id": c["product_id"],
                "product_name": c.get("name_clean") or c.get("name"),
                "name": c.get("name"), "brand": c.get("brand"),
                "category": c.get("category"), "category_kr": CATEGORY_KR.get(c.get("category"), c.get("category")),
                "price": c.get("price"), "rating": c.get("rating"),
                "reviews": c.get("reviews"), "image": c.get("image"),
                "link": c.get("link"), "volume": c.get("volume"),
                "llm_score": score, "picked_by": picked,
                "retrieval_rank": c.get("retrieval_rank"),
                "matched_symptoms": [s for s in ranked_symptoms(levels)
                                     if (c.get("symptom_scores") or {}).get(s, 0) > 0],
                "reason": gentle_reason(c) if all_zero else _evidence_reason(c, levels),
                "evidence_note": evidence_note(c, levels),
            })
        return {
            "status": "ok", "levels": levels, "priority": ranked_symptoms(levels),
            "query": found["query"], "candidate_count": len(candidates),
            "candidate_ids": [c["product_id"] for c in candidates],
            "categories": list(dict.fromkeys(item[0]["category"] for item in chosen)),
            "recommendations": results, "llm_available": bool(calls),
            "llm_calls": calls, "all_zero": all_zero,
            "retrieval": {"embedding_count": found["embedding_count"],
                          "ingredient_count": found["ingredient_count"]},
            "prompt_chars": prompt_chars,
            "timing_ms": {"total_ms": int((time.perf_counter()-started)*1000)},
        }


def _evidence_reason(candidate, levels):
    note = evidence_note(candidate, levels)
    if note:
        return f"현재 두피 증상에 참고할 수 있는 성분 근거가 확인되었습니다. ({note})"
    return "상품 설명과 두피 상태를 종합하여 Qwen 적합도 평가에서 선택되었습니다. 등록된 성분 근거는 제한적입니다."


def print_result(result):
    print("후보:", result.get("candidate_count"), "상태:", result.get("status"))
    for x in result.get("recommendations", []):
        print(f"{x['rank']}. {x['product_name']} | {x['category_kr']} | {x['llm_score']}점")
        print("  ", x["reason"])
