"""
LLM 출력 검증

LLM 이 후보에 없는 상품을 만들어 내는 것을 여기서 막는다.
방식은 번호 검증이다. 상품명이 아니라 product_id 로 받고,
후보 목록에 없는 번호는 버린다. 이름은 LLM 응답을 쓰지 않고 DB 값으로 덮어쓴다.
이름을 덮어쓰면 LLM 이 이름을 잘못 적어도 사용자에게 잘못된 이름이 나가지 않는다.

알레르기 주의 문구도 LLM 응답을 쓰지 않는다.
규칙으로 계산한 매칭 결과에서 문장을 만들어 붙인다.
LLM 에게는 판단을 맡기지 않고 표현만 맡긴다.

증상이 모두 0단계인 경우는 LLM 을 아예 쓰지 않는다. pick_gentle 을 쓴다.
설명할 증상이 없으면 LLM 이 제품 설명을 베끼거나 다른 후보의 이름을 끌어왔다.
"""

from recommendation.config import FINAL_MAX, FINAL_MIN, SYMPTOMS
from recommendation.llm.recommendation_prompt import evidence_note
from recommendation.preprocessing.gentleness import gentle_reason

META_FIELDS = ["name", "name_clean", "brand", "category", "volume", "price",
               "rating", "reviews", "link", "image", "active_ingredients",
               "symptom_scores", "score_evidence", "similarity", "retrieval_rank",
               "gentleness", "gentle_absent", "gentle_present"]


def parse_and_validate(llm_output, candidates, levels=None,
                       pick=None, require_category=None):
    """
    llm_output       : LLM 이 돌려준 dict
    candidates       : 프롬프트에 넣은 후보 목록
    levels           : 증상 레벨. matched_symptoms 검증에 쓴다.
    pick             : 개수를 이 값으로 고정한다. None 이면 FINAL_MIN~FINAL_MAX 범위.
    require_category : 이 카테고리가 아닌 상품은 버린다. 카테고리 단위 호출에서 쓴다.

    반환: (추천 목록, 검증 로그)
    """
    by_id = {c["product_id"]: c for c in candidates}
    levels = levels or {}
    lo = hi = pick
    if pick is None:
        lo, hi = FINAL_MIN, FINAL_MAX
    log = {"dropped_unknown_id": [], "dropped_duplicate": [],
           "dropped_level0_symptom": [], "dropped_wrong_category": [],
           "filled_from_retrieval": 0, "trimmed": 0}

    items = []
    if isinstance(llm_output, dict):
        items = llm_output.get("recommendations") or llm_output.get("recommendation") or []
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        items = []

    picked, seen = [], set()
    for it in items:
        if not isinstance(it, dict):
            continue
        pid = _to_int(it.get("product_id"))
        if pid is None or pid not in by_id:
            log["dropped_unknown_id"].append(it.get("product_id"))
            continue
        if pid in seen:
            log["dropped_duplicate"].append(pid)
            continue
        if require_category and by_id[pid].get("category") != require_category:
            log["dropped_wrong_category"].append(pid)
            continue
        seen.add(pid)

        matched = [s for s in (it.get("matched_symptoms") or []) if s in SYMPTOMS]
        kept = [s for s in matched if levels.get(s, 0) > 0] if levels else matched
        if len(kept) < len(matched):
            log["dropped_level0_symptom"].extend([s for s in matched if s not in kept])

        picked.append({
            "product_id": pid,
            "reason": str(it.get("reason") or "").strip(),
            "matched_symptoms": kept,
            "picked_by": "llm",
        })

    # 개수가 모자라면 검색 순위대로 채운다. LLM 이 적게 돌려준 경우에 대비.
    if len(picked) < lo:
        for c in candidates:
            if len(picked) >= lo:
                break
            if c["product_id"] in seen:
                continue
            if require_category and c.get("category") != require_category:
                continue
            seen.add(c["product_id"])
            picked.append({
                "product_id": c["product_id"],
                "reason": "",
                "matched_symptoms": [s for s in SYMPTOMS
                                     if levels.get(s, 0) > 0
                                     and c["symptom_scores"].get(s, 0) > 0][:2],
                "picked_by": "fallback",
            })
            log["filled_from_retrieval"] += 1

    if len(picked) > hi:
        log["trimmed"] = len(picked) - hi
        picked = picked[:hi]

    # 메타데이터 결합. 이름과 주의 문구는 DB·규칙 값으로 덮어쓴다.
    out = []
    for rank, p in enumerate(picked, start=1):
        c = by_id[p["product_id"]]
        rec = {k: c.get(k) for k in META_FIELDS}
        rec.update({
            "rank": rank,
            "product_id": p["product_id"],
            "product_name": c.get("name_clean") or c.get("name"),
            "reason": p["reason"],
            "matched_symptoms": p["matched_symptoms"],
            "picked_by": p["picked_by"],
            # 근거 성분은 LLM 응답을 쓰지 않고 코드가 데이터에서 만든다.
            # LLM 이 성분을 틀려도 사용자 화면에는 나가지 않는다.
            "evidence_note": evidence_note(c, levels),
            # 알레르기 주의 문구는 별도 모듈이 생기면 그때 채운다.
            "caution": None,
        })
        out.append(rec)

    return out, log


def pick_gentle(candidates, pick=3):
    """
    증상이 모두 0단계일 때 쓰는 경로. LLM 을 호출하지 않는다.

    순한 정도 내림차순으로 고르고, 같은 점수면 검색 순위를 따른다.
    이유 문장도 코드가 만든다. 그래야 '순한 제품을 골랐다' 는 말이 사실이 된다.
    순한 정도를 보지 않고 검색 순위로만 고르면 그 문장이 거짓이 된다.

    반환 형태는 parse_and_validate 와 같다.
    """
    ranked = sorted(
        candidates,
        key=lambda c: (-float(c.get("gentleness") or 0),
                       c.get("retrieval_rank") or 999),
    )[:pick]

    out = []
    for rank, c in enumerate(ranked, start=1):
        rec = {k: c.get(k) for k in META_FIELDS}
        rec.update({
            "rank": rank,
            "product_id": c["product_id"],
            "product_name": c.get("name_clean") or c.get("name"),
            "reason": gentle_reason(c),
            "matched_symptoms": [],
            "picked_by": "gentleness",
            "evidence_note": " · ".join(c.get("gentle_absent") or []),
            "caution": None,
        })
        out.append(rec)

    log = {"dropped_unknown_id": [], "dropped_duplicate": [],
           "dropped_level0_symptom": [], "dropped_wrong_category": [],
           "filled_from_retrieval": 0, "trimmed": 0,
           "picked_by_gentleness": len(out)}
    return out, log


def _to_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    from recommendation.retrieval.retriever import Retriever

    r = Retriever(backend="hashing")
    res = r.retrieve_category({"dandruff": 1, "hair_loss": 2}, "shampoo",
                              profile={"age_group": "20대"})
    cands = res["candidates"]
    ok_id = cands[0]["product_id"]

    fake = {"recommendations": [
        {"rank": 1, "product_id": ok_id, "product_name": "엉뚱한 이름",
         "reason": "탈모 적합도가 높음", "matched_symptoms": ["hair_loss", "excess_sebum"]},
        {"rank": 2, "product_id": 99999, "product_name": "존재하지 않는 샴푸",
         "reason": "지어낸 상품", "matched_symptoms": ["hair_loss"]},
        {"rank": 3, "product_id": ok_id, "reason": "중복", "matched_symptoms": []},
    ]}
    recs, log = parse_and_validate(fake, cands, res["levels"])
    print("검증 로그:", log)
    for x in recs:
        print(f"{x['rank']}. id {x['product_id']} {x['product_name'][:30]}"
              f" | {x['matched_symptoms']} | {x['picked_by']}")
        print(f"    근거 성분: {x['evidence_note'] or '없음'}")
