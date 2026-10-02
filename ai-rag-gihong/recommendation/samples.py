"""
테스트용 샘플 입력

전부 가짜 데이터다. 실제 사용자 정보가 아니므로 저장소에 올려도 된다.
실제 사용자 기록은 이 파일에 넣지 않는다.

같은 증상에 개인정보만 다른 사용자를 나란히 두었다.
추천이 달라지는지가 개인화가 작동하는지 보는 기준이다.
라마 3.1 8B 는 아래 1~4번이 완전히 같은 결과를 냈다.

알레르기 프로필은 뺐다. 알레르기는 별도 모듈(Allergy RAG)로 분리할 예정이고,
그전까지는 추천 경로에서 다루지 않는다.

    python -m recommendation.samples                  전부 실행
    python -m recommendation.samples --case 3         3번만
    python -m recommendation.samples --no-llm         검색 결과만 확인
    python -m recommendation.samples --model exaone3.5:7.8b
"""

import argparse

from recommendation.config import CATEGORY_KR, LLM_MODEL, SYMPTOM_KR
from recommendation.llm.llama_client import LlamaClient
from recommendation.retrieval.retriever import Retriever
from recommendation.service.recommendation_service import RecommendationService

# ── 비전 모델 출력 샘플 ─────────────────────────────────
SCALP_CASES = {
    "비듬1_탈모2": {"dandruff": 1, "hair_loss": 2},
    "각질3_피지2": {"micro_keratin": 3, "excess_sebum": 2},
    "홍반2_농포2": {"follicular_erythema": 2, "follicular_pustule": 2},
    "전증상_중증": {"micro_keratin": 3, "excess_sebum": 3, "follicular_erythema": 2,
                    "follicular_pustule": 2, "dandruff": 3, "hair_loss": 3},
    "전부_양호":   {},
}

# ── 사용자 개인정보 샘플 (가짜) ──────────────────────────
PROFILES = {
    "미등록":        {},
    "10대_매일":     {"age_group": "10대", "wash_frequency": "하루 1회"},
    "30대_매일":     {"age_group": "30대", "wash_frequency": "하루 1회"},
    "50대_이틀에한번": {"age_group": "50대 이상", "wash_frequency": "2일에 1회"},
    "2만원_이하":    {"age_group": "20대", "max_price": 20000},
    "6만원_이하":    {"age_group": "40대", "wash_frequency": "하루 2회", "max_price": 60000},
}

# ── 실행할 조합 ─────────────────────────────────────────
# (두피 케이스, 프로필, 추천 카테고리)
# 카테고리를 None 으로 두면 코드 규칙이 정한다.
#
# 1~4번은 증상이 같고 개인정보만 다르다. 결과가 달라져야 개인화가 작동하는 것이다.
CASES = [
    ("비듬1_탈모2", "미등록",         None),
    ("비듬1_탈모2", "10대_매일",       None),
    ("비듬1_탈모2", "50대_이틀에한번",  None),
    ("비듬1_탈모2", "2만원_이하",      None),
    ("각질3_피지2", "미등록",          None),
    ("각질3_피지2", "6만원_이하",      None),
    ("홍반2_농포2", "30대_매일",       None),
    ("전증상_중증", "50대_이틀에한번",  None),
    ("전부_양호",   "10대_매일",       ["shampoo"]),
]


def describe(symptoms: dict) -> str:
    on = [f"{SYMPTOM_KR[k]} {v}" for k, v in symptoms.items() if v]
    return ", ".join(on) or "전 증상 0단계"


def profile_line(p: dict) -> str:
    if not p:
        return "등록 정보 없음"
    bits = []
    if p.get("age_group"):
        bits.append(p["age_group"])
    if p.get("wash_frequency"):
        bits.append(p["wash_frequency"])
    if p.get("max_price"):
        bits.append(f"{p['max_price']:,}원 이하")
    return " · ".join(bits)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", type=int, help="1부터 시작하는 번호. 생략하면 전부")
    ap.add_argument("--model", default=LLM_MODEL)
    ap.add_argument("--no-llm", dest="use_llm", action="store_false", default=True)
    ap.add_argument("--backend", default="auto", choices=["auto", "st", "hashing"])
    ap.add_argument("--full-ingredients", action="store_true")
    args = ap.parse_args(argv)

    retriever = Retriever(backend=args.backend)
    svc = RecommendationService(retriever=retriever, llm=LlamaClient(model=args.model))

    if args.use_llm:
        ok, msg = svc.llm.available()
        print(f"모델 {args.model} — {'사용 가능' if ok else '사용 불가'}")
        if not ok:
            print(f"  {msg.splitlines()[0]}")
    print()

    cases = CASES if args.case is None else [CASES[args.case - 1]]
    start = 1 if args.case is None else args.case

    for i, (scase, pcase, plan) in enumerate(cases, start=start):
        print("=" * 72)
        print(f"[{i}] 두피: {describe(SCALP_CASES[scase])}")
        print(f"    사용자: {profile_line(PROFILES[pcase])}   ({pcase})")

        out = svc.recommend(
            SCALP_CASES[scase], PROFILES[pcase], plan=plan,
            include_full_ingredients=args.full_ingredients,
            use_llm=args.use_llm,
        )
        print(f"    카테고리: {[CATEGORY_KR[c] for c in out['categories']]}"
              f"{' (코드 규칙)' if plan is None else ' (지정)'}"
              f"   LLM 호출 {out['llm_calls']}회"
              f"   총 {out['timing_ms']['total_ms']}ms")
        if out["note"]:
            print(f"    참고: {out['note'][:110]}")
        print()

        for cat, block in out["by_category"].items():
            v = block["validation"]
            flags = []
            if v.get("dropped_unknown_id"):
                flags.append(f"허위id {len(v['dropped_unknown_id'])}")
            if v.get("dropped_wrong_category"):
                flags.append(f"타카테고리 {len(v['dropped_wrong_category'])}")
            if v.get("filled_from_retrieval"):
                flags.append(f"검색순위로채움 {v['filled_from_retrieval']}")
            if v.get("picked_by_gentleness"):
                flags.append(f"순한정도로선택 {v['picked_by_gentleness']}")
            print(f"  ── {CATEGORY_KR[cat]} (후보 {block['candidate_count']}개"
                  f"{', ' + ' / '.join(flags) if flags else ''})")
            for r in block["recommendations"]:
                print(f"     {r['category_rank']}. {r['product_name'][:38]}"
                      f"  [검색{r['retrieval_rank']}위] {r['price']:,}원")
                if r["reason"]:
                    print(f"        {r['reason']}")
                if r.get("evidence_note"):
                    label = "근거" if r["picked_by"] == "gentleness" else "근거 성분"
                    print(f"        {label} — {r['evidence_note']}")
            print()

    print("=" * 72)
    print("확인할 것")
    print("  1~4번은 증상이 같고 개인정보만 다르다. 추천이 같으면 개인화가 안 되는 것")
    print("  검색순위가 매번 같은 번호면 모델이 비교 없이 집은 것")
    print("  허위id·타카테고리가 0 이 아니면 모델이 목록 밖을 적어낸 것 (코드가 버림)")
    print("  이유 문장에 성분 이름·리뷰 수·가격·상품명이 나오면 규칙 위반")
    print("     넷 다 코드가 화면에 따로 찍는다")
    print("  9번은 LLM 호출 0회다. 증상이 전부 0단계라 코드가 이유를 쓴다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
