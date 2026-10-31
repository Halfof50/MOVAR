"""Only verified product-data evidence is used for display text."""
from app.config import SYMPTOMS, SYMPTOM_KR


def evidence_note(candidate: dict, levels: dict) -> str:
    scores = candidate.get("symptom_scores") or {}
    evidence = candidate.get("score_evidence") or {}
    pieces = []
    for symptom in sorted(SYMPTOMS, key=lambda x: -levels.get(x, 0)):
        if levels.get(symptom, 0) <= 0 or float(scores.get(symptom, 0) or 0) <= 0:
            continue
        vals = [str(v) for v in (evidence.get(symptom) or []) if v]
        if vals:
            pieces.append(f"{SYMPTOM_KR[symptom]}: {', '.join(vals)}")
    return " · ".join(pieces)
