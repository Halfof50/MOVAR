"""
추천 파이프라인

카테고리 하나당 LLM 을 한 번 호출한다.
샴푸·토닉·트리트먼트를 추천해야 하면 세 번 호출하고 각각 3개씩 받는다.

    증상 레벨 + 사용자 정보 + 추천할 카테고리 목록
        │
        └─ 카테고리마다 반복
              Query 생성 (카테고리 지정)
              → 임베딩 → 같은 카테고리 안에서 후보 12개
              → 성분 적합도 결합
              → 프롬프트 (후보 12개 전부 같은 유형)
              → 로컬 LLM → 3개 선택 + 이유
              → 번호·카테고리 검증, 이름·주의문구 덮어쓰기
        │
        └─ 카테고리별 결과를 합쳐서 반환

한 호출에 한 유형만 넣는 이유.
  후보가 모두 같은 유형이면 모델은 증상 적합도만 비교하면 된다.
  '샴푸를 포함해라', '유형을 섞어라', '같은 유형을 중복하지 마라' 같은 제약이
  구조로 보장되어 프롬프트에서 사라진다. 작은 모델일수록 이 차이가 크다.

증상이 모두 0단계면 LLM 을 거치지 않는다.
  설명할 증상이 없으면 프롬프트에 비교할 재료가 남지 않는다.
  측정해 보니 모델이 비워 두는 대신 다른 후보의 제품 설명과 이름을 끌어와
  문장을 만들었다 (3건 중 3건). 이 경로는 순한 정도로 고르고 이유도 코드가 쓴다.

추천할 카테고리는 리포트의 product_plan.combo 가 정한다.
리포트가 없으면 config.FALLBACK_PLAN_RULES 로 코드가 정한다.
"""

import time

from recommendation.config import (
    CANDIDATES_PER_CATEGORY, CATEGORY_KR, CATEGORY_ORDER, FALLBACK_PLAN_RULES,
    MAX_CATEGORIES, PICK_PER_CATEGORY, SYMPTOM_KR,
)
from recommendation.llm.llama_client import LlamaClient
from recommendation.llm.output_parser import parse_and_validate, pick_gentle
from recommendation.llm.recommendation_prompt import build_category_prompt
from recommendation.retrieval.query_builder import normalize_levels, ranked_symptoms
from recommendation.retrieval.retriever import Retriever


def resolve_categories(plan=None, report=None, levels=None) -> list:
    """
    추천할 카테고리 목록을 정한다.

    plan   : ["shampoo", "tonic"] 또는 리포트의 combo 배열
             [{"category": "shampoo", "count": 1, ...}, ...]
    report : 리포트 전체. plan 이 없으면 product_plan.combo 를 꺼낸다.
    levels : 둘 다 없을 때 코드 규칙으로 정하기 위한 증상 레벨
    """
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

        # 증상이 모두 0단계면 LLM 을 쓰지 않는다.
        # 설명할 증상이 없으면 LLM 이 쓸 것도 없는데, 측정해 보니 비워 두지 않고
        # 다른 후보의 제품 설명과 이름을 끌어와 문장을 만들었다 (3건 / 3건).
        # 이 경우는 순한 정도로 고르고 이유도 코드가 쓴다.
        all_zero = not any(levels.values())

        llm_ok, llm_msg = (self.llm.available() if (use_llm and not all_zero)
                           else (False, "LLM 사용이 꺼져 있습니다."))

        by_category, flat, notes = {}, [], []
        for cat in categories:
            t1 = time.time()
            res = self.retriever.retrieve_category(levels, cat, profile, top_k=top_k)
            cands = res["candidates"]

            if not cands:
                by_category[cat] = {
                    "query": res["query"], "candidate_count": 0,
                    "recommendations": [], "validation": {},
                    "note": f"{CATEGORY_KR[cat]} 후보가 없습니다.", "timing_ms": {},
                }
                notes.append(by_category[cat]["note"])
                continue

            # ── 증상이 모두 0단계인 경로. LLM 을 거치지 않는다 ──
            if all_zero:
                recs, log = pick_gentle(cands, pick=pick)
                for r in recs:
                    r["category_rank"] = r["rank"]
                flat.extend(recs)
                note = ("증상이 모두 0단계여서 순한 정도로 골랐습니다. "
                        "이유 문장은 코드가 작성했습니다.")
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
                    "timing_ms": {"retrieve_ms": int((time.time() - t1) * 1000),
                                  "llm_ms": 0},
                }
                continue

            prompt = build_category_prompt(
                levels, profile, cands, cat, pick=pick,
                include_full_ingredients=include_full_ingredients, shuffle=shuffle)

            llm_output, note = None, None
            t2 = time.time()
            if llm_ok:
                try:
                    llm_output = self.llm.generate_json(prompt)
                except Exception as e:
                    note = (f"{CATEGORY_KR[cat]}: LLM 호출 실패로 검색 순위를 사용했습니다. "
                            f"{type(e).__name__}: {e}")
            else:
                # 카테고리마다 같은 메시지가 반복되지 않게 이유는 한 번만 적는다.
                note = f"LLM 을 사용할 수 없어 검색 순위를 사용했습니다. {llm_msg.splitlines()[0]}"
            llm_ms = int((time.time() - t2) * 1000)

            recs, log = parse_and_validate(
                llm_output or {}, cands, levels, pick=pick, require_category=cat)
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
                "timing_ms": {"retrieve_ms": int((t2 - t1) * 1000), "llm_ms": llm_ms},
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
            # 0단계 경로는 LLM 을 거치지 않으므로 카테고리 수와 호출 수가 다르다
            "llm_calls": 0 if all_zero else sum(
                1 for b in by_category.values() if b["candidate_count"]),
            "all_zero": all_zero,
            "note": "; ".join(notes) or None,
            "timing_ms": {"total_ms": int((time.time() - t0) * 1000)},
        }


def print_result(result: dict):
    print("증상 :", ", ".join(f"{SYMPTOM_KR[k]} {v}" for k, v in result["levels"].items() if v))
    print("우선순위:", [SYMPTOM_KR[s] for s in result["priority"]])
    print("추천 카테고리:", [CATEGORY_KR[c] for c in result["categories"]],
          f"→ LLM 호출 {len(result['categories'])}회")
    print("총 소요:", result["timing_ms"]["total_ms"], "ms")
    if result["note"]:
        print("참고 :", result["note"])
    print()

    for cat, block in result["by_category"].items():
        print(f"── {CATEGORY_KR[cat]} "
              f"(후보 {block['candidate_count']}개, 프롬프트 {block.get('prompt_chars', 0):,}자,"
              f" {block.get('timing_ms')}) ──")
        print(f"   검증 {block['validation']}")
        for r in block["recommendations"]:
            fit = ", ".join(f"{SYMPTOM_KR[k]} {v:.1f}"
                            for k, v in r["symptom_scores"].items() if v > 0)
            print(f"   {r['category_rank']}. {r['product_name'][:40]}")
            print(f"      검색순위 {r['retrieval_rank']}  유사도 {r['similarity']}"
                  f"  {r['price']:,}원  평점 {r['rating']}  [{r['picked_by']}]")
            print(f"      적합도 {fit or '없음'}")
            if r["reason"]:
                print(f"      이유 {r['reason']}")
            if r.get("evidence_note"):
                print(f"      근거 {r['evidence_note']}")
        print()


if __name__ == "__main__":
    svc = RecommendationService(backend="hashing")

    # 리포트가 샴푸+토닉 조합을 냈다고 가정
    fake_report = {"product_plan": {"combo": [
        {"category": "shampoo", "count": 1, "target": "hair_loss"},
        {"category": "tonic", "count": 1, "target": "hair_loss"},
    ]}}

    result = svc.recommend(
        {"dandruff": 1, "hair_loss": 2},
        {"age_group": "30대", "wash_frequency": "하루 1회", "max_price": 60000},
        report=fake_report,
    )
    print_result(result)

    print("=" * 64)
    print("리포트 없을 때 (코드 규칙으로 카테고리 결정)")
    for sym, label in [({"micro_keratin": 3, "excess_sebum": 2}, "각질3 피지2"),
                       ({"hair_loss": 3}, "탈모3"),
                       ({"follicular_pustule": 2, "dandruff": 1}, "농포2 비듬1"),
                       ({}, "전부 0")]:
        cats = resolve_categories(levels=normalize_levels(sym))
        print(f"  {label:14s} → {[CATEGORY_KR[c] for c in cats]}")
