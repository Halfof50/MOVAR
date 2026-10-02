"""
동작 점검

    python -m recommendation.tests.test_pipeline

pytest 없이 돌아간다. 인덱스가 먼저 만들어져 있어야 한다.
임베딩 모델 없이 확인하려면 환경변수 MOVAR_TEST_BACKEND=hashing 로 둔다.

알레르기는 추천 경로에서 빠졌다. allergen_mapper 자체의 단위 테스트는 남겨둔다.
나중에 별도 모듈(Allergy RAG)의 1차 필터로 쓸 모듈이라 매칭 정확도는 계속 지켜야 한다.
"""

import os

from recommendation.config import FINAL_MAX, FINAL_MIN, SYMPTOMS
from recommendation.llm.output_parser import parse_and_validate
from recommendation.preprocessing.allergen_mapper import (
    contact_allergens, food_allergen_matches,
)
from recommendation.preprocessing.ingredient_normalizer import find_ingredients
from recommendation.preprocessing.ingredient_scores import ingredient_scores
from recommendation.retrieval.query_builder import build_query, normalize_levels
from recommendation.retrieval.retriever import Retriever

BACKEND = os.getenv("MOVAR_TEST_BACKEND", "hashing")
passed, failed = 0, []


def check(name, cond, detail=""):
    global passed
    if cond:
        passed += 1
        print(f"  OK   {name}")
    else:
        failed.append(f"{name} {detail}")
        print(f"  FAIL {name} {detail}")


print("[성분 정규화]")
check("바이오틴 표기를 비오틴으로 매칭",
      "비오틴" in find_ingredients("정제수, 바이오틴, 글리세린"))
check("하이드록시에틸우레아를 유레아로 보지 않음",
      "유레아" not in find_ingredients("정제수, 하이드록시에틸우레아"))
check("차나무를 티트리로 보지 않음",
      "티트리" not in find_ingredients("정제수, 유차나무씨오일"))
check("티트리잎오일은 티트리로 매칭",
      "티트리" in find_ingredients("정제수, 티트리잎오일"))
check("공백만으로 나열한 전성분도 처리",
      "피록톤올아민" in find_ingredients(
          "정제수 소듐라우레스설페이트 피록톤올아민 멘톨 살리실릭애씨드 " * 2))

print("\n[성분 점수]")
s, _ = ingredient_scores("정제수, 덱스판테놀, 살리실릭애씨드, 엘-멘톨")
check("고시 조합 A 충족 시 탈모 1.0 이상", s["hair_loss"] >= 1.0, f"= {s['hair_loss']}")

# 고시 조합을 1.0 으로 대입하면 성분 개수 가산분이 지워진다.
# 성분이 많아 가산 결과가 1.0 을 넘는 경우에 그 값이 유지되는지 본다.
s_many, _ = ingredient_scores(
    "정제수, 덱스판테놀, 살리실릭애씨드, 엘-멘톨, 비오틴, 나이아신아마이드, 징크피리치온, 카페인")
check("고시 조합이 성분 개수 가산분을 지우지 않음", s_many["hair_loss"] > 1.0,
      f"= {s_many['hair_loss']}")
s2, _ = ingredient_scores("정제수, 글리세린")
check("유효 성분 없으면 전부 0", all(v == 0 for v in s2.values()))
s3, _ = ingredient_scores("정제수, 피록톤올아민, 클림바졸, 징크피리치온")
check("같은 증상 여러 성분이면 최댓값+가산", s3["dandruff"] > 1.0, f"= {s3['dandruff']}")

print("\n[알레르기 매칭 — 모듈 단위. 추천 경로에서는 호출하지 않는다]")
check("긴 이름 우선 — 헥실신남알만 있을 때 신남알을 따로 세지 않음",
      contact_allergens("정제수, 헥실신남알") == ["헥실신남알"])
check("단독 신남알은 잡음",
      "신남알" in contact_allergens("정제수, 신남알, 헥실신남알"))
check("락토바실러스를 우유로 보지 않음",
      not food_allergen_matches("정제수, 락토바실러스발효물", ["우유"]))
check("약모밀을 메밀로 보지 않음",
      not food_allergen_matches("정제수, 약모밀추출물", ["메밀"]))
check("스위트아몬드오일을 밀로 보지 않음",
      not food_allergen_matches("정제수, 스위트아몬드오일", ["밀"]))
check("밀단백질은 밀로 잡음",
      bool(food_allergen_matches("정제수, 하이드롤라이즈드밀단백질", ["밀"])))
check("인동덩굴을 조개류로 보지 않음",
      not food_allergen_matches("정제수, 인동덩굴꽃추출물", ["조개류"]))
check("코코 계면활성제는 processed 로 분류",
      all(m["level"] == "processed"
          for m in food_allergen_matches("정제수, 코코-글루코사이드", ["코코넛"])))

print("\n[순한 정도 — 증상이 모두 0단계일 때 쓰는 기준]")
from recommendation.preprocessing.gentleness import (
    MAX_SCORE, gentle_reason, gentleness,
)

check("페녹시에탄올을 에탄올로 보지 않음",
      gentleness("정제수, 페녹시에탄올, 글리세린")[0] == MAX_SCORE,
      f"= {gentleness('정제수, 페녹시에탄올, 글리세린')}")
check("세틸알코올을 자극원으로 보지 않음",
      gentleness("정제수, 세틸알코올, 스테아릴알코올")[0] == MAX_SCORE)
check("단독 에탄올은 잡음",
      gentleness("정제수, 에탄올, 글리세린")[0] == MAX_SCORE - 1)
check("소듐라우레스설페이트는 설페이트로 잡음",
      gentleness("정제수, 소듐라우레스설페이트")[0] == MAX_SCORE - 1)
check("티이에이-라우릴설페이트도 설페이트로 잡음",
      gentleness("정제수, 티이에이-라우릴설페이트")[0] == MAX_SCORE - 1)
check("올레핀설포네이트는 설페이트로 보지 않음",
      gentleness("정제수, 소듐C14-16올레핀설포네이트")[0] == MAX_SCORE)
check("향료는 잡고 코코-글루코사이드는 안 잡음",
      gentleness("정제수, 향료")[0] == MAX_SCORE - 1
      and gentleness("정제수, 코코-글루코사이드")[0] == MAX_SCORE)
check("살리실릭애씨드는 각질제거 산으로 잡음",
      gentleness("정제수, 살리실릭애씨드")[0] == MAX_SCORE - 1)
check("자극원이 많을수록 점수가 낮다",
      gentleness("정제수, 소듐라우레스설페이트, 향료, 에탄올, 살리실릭애씨드")[0] == 0.0)

r1 = gentle_reason({"ingredients": "정제수, 소듐라우레스설페이트, 글리세린"})
check("이유 문장이 존댓말로 끝난다", r1.endswith("좋습니다."), f"= {r1[-20:]}")
check("조사가 맞게 붙는다 — 에탄올과",
      "에탄올와" not in r1 and "에탄올과" in r1, f"= {r1}")
r0 = gentle_reason({"ingredients": "정제수, 소듐라우레스설페이트, 향료, 에탄올, 살리실릭애씨드"})
check("자극원이 전부 있으면 무첨가 주장을 하지 않는다",
      "넣지 않은" not in r0, f"= {r0}")
check("이유에 성분 이름을 쓰지 않는다",
      "살리실릭애씨드" not in r0 and "살리실릭애씨드" not in r1)

print("\n[Query]")
lv = normalize_levels({"hair_loss": 2, "dandruff": 1})
q = build_query(lv)
check("심한 증상이 문장 앞에 온다", q.index("탈모") < q.index("비듬"))
check("md 예시 문장 구조와 같다",
      q.startswith("탈모 증상이 2단계로 주요 관리가 필요하며, "
                   "비듬이 1단계로 경미하게 나타난 두피."), f"= {q[:60]}")
check("조사가 맞게 붙는다", "비듬이" in q and "비듬가" not in q)
check("카테고리 꼬리말이 붙지 않는다", "제품 유형은" not in q)
check("레벨 0 증상은 Query 에 없다", "미세각질" not in q)
check("전부 0이면 전용 문장", "특별한 증상이 없는" in build_query({}))
check("레벨 범위를 벗어난 값은 잘린다", normalize_levels({"dandruff": 9})["dandruff"] == 3)

print("\n[검색 / 검증]")
r = Retriever(backend=BACKEND)
res = r.retrieve({"dandruff": 1, "hair_loss": 2}, profile={"max_price": 100000})
cands = res["candidates"]
check("후보가 나온다", len(cands) > 0, f"= {len(cands)}")
check("후보에 성분 점수가 붙어 있다",
      all(set(c["symptom_scores"]) == set(SYMPTOMS) for c in cands))
check("가격 상한이 적용된다", all((c["price"] or 0) <= 100000 for c in cands))
check("카테고리가 섞여 있다", len({c["category"] for c in cands}) >= 2,
      f"= {sorted({c['category'] for c in cands})}")

# 알레르기와 기피 성분은 후보에 붙지 않는다. 추천 경로에서 빠졌다.
check("후보에 알레르기 키가 없다",
      not any("user_allergen_matches" in c or "contact_allergens" in c for c in cands))
check("후보에 기피 성분 키가 없다",
      not any("avoid_matches" in c for c in cands))

res2 = r.retrieve({"dandruff": 1, "hair_loss": 2},
                  profile={"food_allergies": ["밀"], "avoid_ingredients": ["살리실릭애씨드"]})
check("알레르기·기피 성분을 줘도 후보를 걸러내지 않는다",
      len(res2["candidates"]) == len(cands),
      f"{len(res2['candidates'])} vs {len(cands)}")

ok_id = cands[0]["product_id"]
fake = {"recommendations": [
    {"rank": 1, "product_id": ok_id, "product_name": "거짓 이름",
     "reason": "근거", "matched_symptoms": ["hair_loss", "excess_sebum"]},
    {"rank": 2, "product_id": 999999, "product_name": "없는 상품",
     "reason": "환각", "matched_symptoms": ["hair_loss"]},
    {"rank": 3, "product_id": ok_id, "reason": "중복", "matched_symptoms": []},
]}
recs, log = parse_and_validate(fake, cands, res["levels"])
check("후보에 없는 id 는 버린다", 999999 in [x for x in log["dropped_unknown_id"]])
check("중복 id 는 버린다", ok_id in log["dropped_duplicate"])
check("레벨 0 증상은 근거에서 뺀다", "excess_sebum" in log["dropped_level0_symptom"])
check("상품명을 DB 값으로 덮어쓴다", recs[0]["product_name"] != "거짓 이름")
check("최소 개수를 채운다", len(recs) >= FINAL_MIN, f"= {len(recs)}")
check("알레르기 주의 문구는 비어 있다", all(x["caution"] is None for x in recs))

many = {"recommendations": [
    {"rank": i, "product_id": c["product_id"], "reason": "x", "matched_symptoms": []}
    for i, c in enumerate(cands[:10], start=1)]}
recs2, log2 = parse_and_validate(many, cands, res["levels"])
check("최대 개수를 넘지 않는다", len(recs2) == FINAL_MAX, f"= {len(recs2)}")

print("\n[근거 성분 문구 — 코드가 만든다]")
from recommendation.llm.recommendation_prompt import evidence_note

with_evidence = [x for x in recs if x["evidence_note"]]
check("근거 성분 문구가 붙는다", bool(with_evidence),
      f"= {[x['evidence_note'] for x in recs]}")
if with_evidence:
    note = with_evidence[0]["evidence_note"]
    check("레벨 0 증상은 근거 문구에 없다", "미세각질" not in note and "농포" not in note,
          f"= {note}")

# 점수가 0인 증상은 근거 성분이 없으므로 문구에 나오지 않아야 한다
no_score = next((c for c in cands if c["symptom_scores"]["hair_loss"] == 0), None)
if no_score:
    check("점수 0인 증상은 근거 문구에 안 쓴다",
          "탈모" not in evidence_note(no_score, res["levels"]),
          f"= {evidence_note(no_score, res['levels'])}")

# 전성분에 등록 성분이 하나도 없으면 문구는 빈 문자열
check("근거 성분이 없으면 빈 문구",
      evidence_note({"symptom_scores": {s: 0 for s in SYMPTOMS}, "score_evidence": {}},
                    res["levels"]) == "")

print("\n[카테고리 단위 추천]")
from recommendation.config import PICK_PER_CATEGORY
from recommendation.llm.recommendation_prompt import build_category_prompt
from recommendation.service.recommendation_service import (
    RecommendationService, resolve_categories,
)

cat_res = r.retrieve_category({"dandruff": 1, "hair_loss": 2}, "shampoo")
cc = cat_res["candidates"]
check("한 카테고리만 검색된다", {c["category"] for c in cc} == {"shampoo"},
      f"= {sorted({c['category'] for c in cc})}")
check("후보 개수가 설정값 이하", len(cc) <= 12, f"= {len(cc)}")

cp = build_category_prompt(res["levels"], {}, cc, "shampoo", pick=3)
check("정확히 3개를 고르라는 규칙이 들어간다", "정확히 3개를 고른다" in cp)
check("샴푸 포함 규칙이 사라졌다", "샴푸를 최소 1개" not in cp)
check("유형 섞기 규칙이 사라졌다", "서로 다른 제품 유형을 섞고" not in cp)

# 다른 카테고리 상품을 섞어 응답하면 버려야 한다
other = next(c for c in cands if c["category"] != "shampoo")
mixed_out = {"recommendations": [
    {"rank": 1, "product_id": cc[0]["product_id"], "reason": "a", "matched_symptoms": []},
    {"rank": 2, "product_id": other["product_id"], "reason": "b", "matched_symptoms": []},
]}
crecs, clog = parse_and_validate(mixed_out, cc + [other], res["levels"],
                                 pick=3, require_category="shampoo")
check("다른 카테고리 상품은 버린다",
      other["product_id"] in clog["dropped_wrong_category"])
check("개수를 pick 값으로 맞춘다", len(crecs) == 3, f"= {len(crecs)}")
check("결과가 전부 지정 카테고리", {x["category"] for x in crecs} == {"shampoo"})

print("\n[카테고리 결정]")
check("리포트 combo 를 따른다",
      resolve_categories([{"category": "shampoo"}, {"category": "tonic"}]) ==
      ["shampoo", "tonic"])
check("리포트가 없으면 규칙으로 정한다",
      resolve_categories(levels=normalize_levels({"micro_keratin": 3})) ==
      ["shampoo", "scaler"])
check("증상이 없으면 샴푸만",
      resolve_categories(levels=normalize_levels({})) == ["shampoo"])
check("카테고리 수를 제한한다",
      len(resolve_categories(levels=normalize_levels(
          {"micro_keratin": 3, "hair_loss": 3, "follicular_pustule": 3}))) <= 3)
check("정해진 순서로 정렬된다",
      resolve_categories([{"category": "tonic"}, {"category": "shampoo"}]) ==
      ["shampoo", "tonic"])
check("알 수 없는 카테고리는 무시한다",
      resolve_categories([{"category": "소금"}, {"category": "shampoo"}]) == ["shampoo"])

svc = RecommendationService(retriever=r, llm=None, backend=BACKEND)
out = svc.recommend({"dandruff": 1, "hair_loss": 2}, {"age_group": "30대"},
                    report={"product_plan": {"combo": [
                        {"category": "shampoo"}, {"category": "tonic"}]}},
                    use_llm=False)
check("카테고리 수만큼 블록이 생긴다", len(out["by_category"]) == 2,
      f"= {list(out['by_category'])}")
check("카테고리당 pick 개씩 나온다",
      all(len(b["recommendations"]) == PICK_PER_CATEGORY
          for b in out["by_category"].values()))
check("합친 목록의 순위가 1부터 이어진다",
      [x["rank"] for x in out["recommendations"]] ==
      list(range(1, len(out["recommendations"]) + 1)))
check("LLM 없이도 결과가 나온다", len(out["recommendations"]) == 6,
      f"= {len(out['recommendations'])}")
check("LLM 미사용 사실이 note 에 적힌다", bool(out["note"]))

print("\n[전 증상 0단계 경로 — LLM 을 거치지 않는다]")
zero = svc.recommend({}, {"age_group": "10대", "wash_frequency": "하루 1회"},
                     plan=["shampoo"], use_llm=True)
zb = zero["by_category"]["shampoo"]
zr = zb["recommendations"]
check("LLM 호출이 0회", zero["llm_calls"] == 0, f"= {zero['llm_calls']}")
check("all_zero 로 표시된다", zero["all_zero"] is True)
check("프롬프트를 만들지 않는다", zb["prompt_chars"] == 0)
check("순한 정도로 골랐다고 기록된다",
      zb["validation"].get("picked_by_gentleness") == PICK_PER_CATEGORY)
check("picked_by 가 gentleness", all(x["picked_by"] == "gentleness" for x in zr))
check("이유가 비어 있지 않다", all(x["reason"] for x in zr))
check("순한 정도 내림차순으로 정렬된다",
      [x["gentleness"] for x in zr] == sorted(
          [x["gentleness"] for x in zr], reverse=True),
      f"= {[x['gentleness'] for x in zr]}")
check("이유에 상품명이 없다",
      not any(any(o["product_name"][:10] in x["reason"] for o in zr) for x in zr))
check("이유에 리뷰·가격 표현이 없다",
      not any("리뷰" in x["reason"] or "가격" in x["reason"] or "원" in x["reason"]
              for x in zr))
check("근거 문구가 사실 표기다",
      all(("무첨가" in x["evidence_note"] or "없음" in x["evidence_note"]
           or x["evidence_note"] == "") for x in zr),
      f"= {[x['evidence_note'] for x in zr]}")
check("근거 문구에 '자극' 같은 효능 표현이 없다",
      not any("자극" in (x["evidence_note"] or "") for x in zr))
check("0단계라 matched_symptoms 는 비어 있다",
      all(x["matched_symptoms"] == [] for x in zr))

print("\n[프롬프트]")
p = build_category_prompt(res["levels"], {"age_group": "30대"}, cc, "shampoo", pick=3)
check("사용 가능한 id 목록이 들어간다", "사용 가능한 product_id:" in p)
check("JSON 만 출력 규칙이 들어간다", "JSON 만 출력한다" in p)
check("전성분은 기본적으로 제외된다", "전체 전성분:" not in p)
check("금지 목록에 성분 이름이 들어간다", "성분 이름" in p)
check("금지 목록에 리뷰 수가 들어간다", "리뷰 수" in p)
check("금지 목록에 가격이 들어간다", "가격, 평점, 리뷰 수, 상품명" in p)
check("'이름을 그대로 쓴다' 규칙이 사라졌다",
      "후보 목록에 적힌 이름을 그대로 쓴다" not in p)
check("알레르기 관련 지시가 없다",
      "알레르기" not in p and "food_allergies" not in p)
check("착향제 줄이 없다", "착향제" not in p)
check("레벨 0 증상은 분석 결과 블록에 없다",
      "미세각질: 0단계" not in p and "농포: 0단계" not in p)
check("레벨 0 증상은 금지 목록에 나열된다", "이유에 쓰지 않습니다" in p or "쓰지 않는다" in p)
check("출력 형식에 caution 이 없다", '"caution"' not in p)
check("규칙 개수가 9개", "\n9. " in p and "\n10. " not in p)
check("예시에 리뷰·가격을 쓰지 말라는 나쁜 예가 있다",
      "리뷰 수는 화면에 따로 나온다" in p and "가격도 화면에 따로 나온다" in p)
check("예시에 상품명을 쓰지 말라는 나쁜 예가 있다", "상품명을 적었다" in p)

p2 = build_category_prompt(res["levels"], {}, cc, "shampoo", pick=3,
                           include_full_ingredients=True)
check("옵션을 켜면 전성분이 들어간다", "전체 전성분:" in p2)
check("전성분을 켜면 프롬프트가 길어진다", len(p2) > len(p) * 1.5,
      f"{len(p):,} → {len(p2):,}")

print(f"\n통과 {passed}건, 실패 {len(failed)}건")
for f in failed:
    print("  -", f)
raise SystemExit(1 if failed else 0)
