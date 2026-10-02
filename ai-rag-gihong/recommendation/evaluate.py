"""
검색 단계 평가

지적받은 문제가 '증상이 같으면 추천이 같다', '사용자가 늘면 추천이 겹친다' 였으므로
그것을 숫자로 확인할 수 있어야 한다. 이 스크립트가 보는 것은 네 가지.

  1. 커버리지     전체 상품 중 후보로 한 번이라도 나온 상품의 비율
                  낮으면 소수 상품이 모든 사용자에게 반복해서 추천된다는 뜻
  2. 쏠림         상품별 후보 등장 횟수 상위 목록
  3. 후보 다양성  증상 조합이 다를 때 후보 집합이 실제로 달라지는지 (자카드 유사도)

주의. 이 스크립트는 검색 단계만 본다.
사용자 개인화 정보에 따른 최종 순위 차이는 LLM 단계에서 생기므로 여기 숫자에 반영되지 않는다.

    python -m recommendation.evaluate
    python -m recommendation.evaluate --backend hashing --n 80
"""

import argparse
import itertools
import random
from collections import Counter

from recommendation.config import SYMPTOMS, SYMPTOM_KR
from recommendation.retrieval.retriever import Retriever


def sample_scenarios(n: int, seed: int = 0) -> list:
    """증상 조합 표본.

    레벨이 1개 또는 2개만 올라간 조합을 모두 넣고, 나머지는 무작위로 채운다.
    실제 사용자의 대부분이 소수 증상만 높은 형태라는 가정이다.
    """
    rng = random.Random(seed)
    cases = [{}]                                   # 전부 0
    for s in SYMPTOMS:
        for lv in (1, 2, 3):
            cases.append({s: lv})
    for a, b in itertools.combinations(SYMPTOMS, 2):
        cases.append({a: 2, b: 1})
    while len(cases) < n:
        cases.append({s: rng.randint(0, 3) for s in SYMPTOMS})
    return cases[:max(n, 1)]


def jaccard(a: set, b: set) -> float:
    u = a | b
    return len(a & b) / len(u) if u else 1.0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="auto", choices=["auto", "st", "hashing"])
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--per-category", action="store_true", default=True)
    ap.add_argument("--global-topk", dest="per_category", action="store_false")
    args = ap.parse_args(argv)

    r = Retriever(backend=args.backend)
    total_products = len(r.store)
    scenarios = sample_scenarios(args.n)

    sets, appear, sizes = [], Counter(), []
    for sc in scenarios:
        res = r.retrieve(sc, per_category=args.per_category)
        ids = {c["product_id"] for c in res["candidates"]}
        sets.append(ids)
        appear.update(ids)
        sizes.append(len(ids))

    pairs = [jaccard(sets[i], sets[j])
             for i in range(len(sets)) for j in range(i + 1, len(sets))]

    print(f"인덱스 모델 : {r.store.meta.get('model')}")
    print(f"상품 {total_products}개 / 시나리오 {len(scenarios)}개"
          f" / 검색 방식 {'카테고리별 할당' if args.per_category else '전체 상위 K'}")
    print(f"후보 개수   평균 {sum(sizes)/len(sizes):.1f}  최소 {min(sizes)}  최대 {max(sizes)}")
    print()
    covered = len(appear)
    print(f"1. 커버리지     {covered}/{total_products} = {covered/total_products:.1%}")
    print(f"   한 번도 후보에 오르지 않은 상품 {total_products - covered}개")
    print()
    print("2. 쏠림 (후보 등장 횟수 상위 10)")
    for pid, c in appear.most_common(10):
        rec = next(x for x in r.store.records if x["product_id"] == pid)
        print(f"   {c:3d}/{len(scenarios)}  [{rec['category']:9s}] {rec['name_clean'][:38]}")
    print()
    print(f"3. 후보 다양성  시나리오 쌍 평균 자카드 {sum(pairs)/len(pairs):.3f}"
          f"  (1.0 이면 모든 시나리오가 같은 후보)")
    print(f"   서로 다른 후보 집합 {len({frozenset(s) for s in sets})}개 / {len(sets)}개")
    print()

    print("\n증상별 대표 시나리오 1위 후보")
    for s in SYMPTOMS:
        res = r.retrieve({s: 3})
        top = res["candidates"][0] if res["candidates"] else None
        if top:
            print(f"   {SYMPTOM_KR[s]:8s} → [{top['category']:9s}] {top['name_clean'][:34]}"
                  f"  적합도 {top['symptom_scores'].get(s, 0):.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
