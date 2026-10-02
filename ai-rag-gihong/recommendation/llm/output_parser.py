"""
LLM 후보별 점수 출력 검증 + Python 최종 정렬.

LLM은 product_id를 반환하지 않는다.
후보 1~N 각각의 score와 decision_factors만 반환한다.
Python이 candidate_no를 실제 후보 객체에 연결하고 점수순으로 Top K를 만든다.
"""

from recommendation.config import SYMPTOMS, SYMPTOM_KR
from recommendation.llm.recommendation_prompt import evidence_note
from recommendation.preprocessing.gentleness import gentle_reason

META_FIELDS = [
    "name", "name_clean", "brand", "category", "volume", "price",
    "rating", "reviews", "link", "image", "active_ingredients",
    "symptom_scores", "score_evidence", "similarity", "retrieval_rank",
    "gentleness", "gentle_absent", "gentle_present",
]


def _to_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _to_score(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x < 0 or x > 100:
        return None
    return x


def _allowed_factors(levels: dict, profile: dict = None) -> set:
    allowed = {s for s in SYMPTOMS if levels.get(s, 0) > 0}
    for key, value in (profile or {}).items():
        if value not in (None, "", [], {}):
            allowed.add(key)
    return allowed


def _supported_symptom(candidate: dict, symptom: str) -> bool:
    sc = candidate.get("symptom_scores", {}) or {}
    ev = candidate.get("score_evidence", {}) or {}
    return float(sc.get(symptom, 0) or 0) > 0 or bool(ev.get(symptom))


def _verified_reason(candidate: dict, levels: dict) -> str:
    """LLM 자유문장 없이 실제 score_evidence만으로 사용자 표시용 근거를 만든다."""
    sc = candidate.get("symptom_scores", {}) or {}
    ev = candidate.get("score_evidence", {}) or {}
    parts = []

    for symptom in sorted(SYMPTOMS, key=lambda s: -levels.get(s, 0)):
        if levels.get(symptom, 0) <= 0 or float(sc.get(symptom, 0) or 0) <= 0:
            continue
        vals = [str(x) for x in (ev.get(symptom) or []) if x]
        if vals:
            parts.append(
                f"{SYMPTOM_KR[symptom]} 관련 기준 성분: {', '.join(vals)}"
            )

    if parts:
        return ". ".join(parts) + "."

    return "현재 등록된 성분 근거 기준에서 직접 확인된 활성 증상 관련 성분은 제한적입니다."


def parse_score_evaluations(llm_output, candidates, levels=None, profile=None,
                            pick=3, require_category=None):
    """
    LLM score 출력 → 후보 객체 결합 → Python 점수순 정렬 → Top pick.

    반환: (추천 목록, 검증 로그)
    """
    levels = levels or {}
    allowed = _allowed_factors(levels, profile)
    n = len(candidates)

    log = {
        "invalid_candidate_no": [],
        "duplicate_candidate_no": [],
        "invalid_score": [],
        "missing_candidate_no": [],
        "dropped_decision_factors": [],
        "unsupported_decision_factors": [],
        "filled_from_retrieval": 0,   # 기존 테스트 호환. score 방식에서는 정상 경로 0.
        "dropped_unknown_id": [],     # 기존 테스트 호환. product_id를 LLM이 안 내므로 항상 0.
        "dropped_wrong_category": [],
    }

    items = []
    if isinstance(llm_output, dict):
        items = llm_output.get("evaluations") or []
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        items = []

    seen = set()
    evaluated = []

    for item in items:
        if not isinstance(item, dict):
            continue

        no = _to_int(item.get("candidate_no"))
        if no is None or no < 1 or no > n:
            log["invalid_candidate_no"].append(item.get("candidate_no"))
            continue
        if no in seen:
            log["duplicate_candidate_no"].append(no)
            continue

        score = _to_score(item.get("score"))
        if score is None:
            log["invalid_score"].append({"candidate_no": no, "score": item.get("score")})
            continue

        candidate = candidates[no - 1]
        if require_category and candidate.get("category") != require_category:
            log["dropped_wrong_category"].append(no)
            continue

        seen.add(no)

        raw_factors = item.get("decision_factors") or []
        if not isinstance(raw_factors, list):
            raw_factors = []

        factors = []
        for f in raw_factors:
            if f not in allowed:
                log["dropped_decision_factors"].append({"candidate_no": no, "factor": f})
                continue
            if f in SYMPTOMS and not _supported_symptom(candidate, f):
                log["unsupported_decision_factors"].append({"candidate_no": no, "factor": f})
                continue
            if f not in factors:
                factors.append(f)

        evaluated.append({
            "candidate_no": no,
            "candidate": candidate,
            "llm_score": score,
            "decision_factors": factors,
        })

    log["missing_candidate_no"] = [i for i in range(1, n + 1) if i not in seen]

    # 유효 평가가 pick보다 적을 때만 코드 fallback.
    # 이 경우에도 product_id를 LLM에게 다시 받지 않고 원래 candidate 객체를 사용한다.
    if len(evaluated) < min(pick, n):
        existing = {x["candidate_no"] for x in evaluated}
        for no, candidate in enumerate(candidates, start=1):
            if no in existing:
                continue
            evaluated.append({
                "candidate_no": no,
                "candidate": candidate,
                "llm_score": -1.0,
                "decision_factors": [],
            })
            log["filled_from_retrieval"] += 1
            if len(evaluated) >= min(pick, n):
                break

    # 동일 점수면 기존 검색순위를 보조 tie-breaker로만 사용한다.
    evaluated.sort(
        key=lambda x: (
            -x["llm_score"],
            x["candidate"].get("retrieval_rank") or 999,
        )
    )
    chosen = evaluated[:min(pick, n)]

    out = []
    for rank, item in enumerate(chosen, start=1):
        c = item["candidate"]
        rec = {k: c.get(k) for k in META_FIELDS}
        rec.update({
            "rank": rank,
            "product_id": c["product_id"],
            "product_name": c.get("name_clean") or c.get("name"),
            "candidate_no": item["candidate_no"],
            "llm_score": item["llm_score"],
            "decision_factors": item["decision_factors"],
            "matched_symptoms": [f for f in item["decision_factors"] if f in SYMPTOMS],
            "picked_by": "llm_score" if item["llm_score"] >= 0 else "fallback",
            "reason": _verified_reason(c, levels),
            "evidence_note": evidence_note(c, levels),
            "caution": None,
        })
        out.append(rec)

    return out, log


# 기존 호출부가 남아 있어도 깨지지 않도록 이름을 유지한다.
def parse_and_validate(llm_output, candidates, levels=None, pick=3,
                       require_category=None, profile=None):
    return parse_score_evaluations(
        llm_output, candidates, levels=levels, profile=profile,
        pick=pick, require_category=require_category,
    )


def pick_gentle(candidates, pick=3):
    ranked = sorted(
        candidates,
        key=lambda c: (-float(c.get("gentleness") or 0), c.get("retrieval_rank") or 999),
    )[:pick]

    out = []
    for rank, c in enumerate(ranked, start=1):
        rec = {k: c.get(k) for k in META_FIELDS}
        rec.update({
            "rank": rank,
            "product_id": c["product_id"],
            "product_name": c.get("name_clean") or c.get("name"),
            "candidate_no": None,
            "llm_score": None,
            "decision_factors": [],
            "matched_symptoms": [],
            "picked_by": "gentleness",
            "reason": gentle_reason(c),
            "evidence_note": " · ".join(c.get("gentle_absent") or []),
            "caution": None,
        })
        out.append(rec)

    log = {
        "invalid_candidate_no": [], "duplicate_candidate_no": [],
        "invalid_score": [], "missing_candidate_no": [],
        "dropped_decision_factors": [], "unsupported_decision_factors": [],
        "filled_from_retrieval": 0, "dropped_unknown_id": [],
        "dropped_wrong_category": [], "picked_by_gentleness": len(out),
    }
    return out, log


if __name__ == "__main__":
    fake_candidates = [
        {"product_id": 10, "name": "A", "category": "shampoo", "retrieval_rank": 1,
         "symptom_scores": {"hair_loss": 1.0}, "score_evidence": {"hair_loss": ["판테놀"]}},
        {"product_id": 20, "name": "B", "category": "shampoo", "retrieval_rank": 2,
         "symptom_scores": {"hair_loss": 0.6}, "score_evidence": {"hair_loss": ["카페인"]}},
        {"product_id": 30, "name": "C", "category": "shampoo", "retrieval_rank": 3,
         "symptom_scores": {"hair_loss": 0.8}, "score_evidence": {"hair_loss": ["비오틴"]}},
    ]
    fake = {"evaluations": [
        {"candidate_no": 1, "score": 88, "decision_factors": ["hair_loss"]},
        {"candidate_no": 2, "score": 55, "decision_factors": ["hair_loss"]},
        {"candidate_no": 3, "score": 73, "decision_factors": ["hair_loss"]},
    ]}
    recs, log = parse_score_evaluations(fake, fake_candidates, {"hair_loss": 3}, pick=3)
    print(log)
    for r in recs:
        print(r["rank"], r["product_id"], r["llm_score"], r["reason"])
