"""
Document 구성 비교 (ablation)

'임베딩 문장에 유효성분을 넣는 게 효과가 있나'를 추측으로 답하지 않기 위한 스크립트다.
줄을 넣고 빼면서 같은 시나리오로 검색해 결과가 어떻게 달라지는지 본다.

보는 지표
  커버리지   전체 상품 중 후보로 한 번이라도 나온 비율. 높을수록 추천이 덜 겹친다
  자카드     시나리오 쌍의 후보 집합이 얼마나 같은지. 낮을수록 증상에 따라 결과가 달라진다
  적중률     후보의 성분 적합도가 그 시나리오의 주 증상에 대해 0 보다 큰 비율
             (임베딩이 증상과 관련 있는 상품을 실제로 데려오는지)

    python -m recommendation.ablation
    python -m recommendation.ablation --backend hashing

주의. 대체 백엔드(hashing)는 문자 겹침만 보므로 줄을 추가하면 기계적으로 유리해진다.
판단에 쓸 숫자는 실제 임베딩 모델로 돌린 결과뿐이다.
"""

import argparse
import itertools
from collections import Counter

import pandas as pd

from recommendation.config import CATEGORY_QUOTA, PRODUCTS_CSV, SYMPTOMS, SYMPTOM_KR
from recommendation.embedding.embedding_model import get_embedder
from recommendation.embedding.vector_store import VectorStore
from recommendation.evaluate import jaccard, sample_scenarios
from recommendation.preprocessing.allergen_mapper import allergen_info
from recommendation.preprocessing.product_document import build_record
from recommendation.retrieval.query_builder import (
    build_query, normalize_levels, ranked_symptoms,
)

VARIANTS = {
    "상품명만":              {"name"},
    "상품명+카테고리":        {"name", "category"},
    "+유효성분":             {"name", "category", "spec", "actives"},
    "+관리목적":             {"name", "category", "spec", "purpose"},
    "전부 (현재 기본값)":     {"name", "category", "spec", "actives", "purpose"},
}


def build_store(df, parts, embedder):
    records = []
    for i, row in df.iterrows():
        rec = build_record(row, product_id=i + 1, parts=parts)
        rec.update(allergen_info(row.get("ingredients", "")))
        records.append(rec)
    texts = [r["embed_text"] for r in records]
    if getattr(embedder, "requires_fit", False):
        embedder.fit(texts)
    return VectorStore.build(records, embedder.encode(texts), embedder.name), texts


def run(store, embedder, scenarios):
    sets, appear, hit_num, hit_den, sizes = [], Counter(), 0, 0, []
    for sc in scenarios:
        levels = normalize_levels(sc)
        pri = ranked_symptoms(levels)
        qvecs = {c: embedder.encode([build_query(levels)])[0]
                 for c in CATEGORY_QUOTA}
        cands = store.search_by_category(qvecs, CATEGORY_QUOTA)
        if not cands:
            continue
        sets.append({c["product_id"] for c in cands})
        appear.update(c["product_id"] for c in cands)
        sizes.append(len(cands))
        if pri:
            top = pri[0]
            hit_num += sum(1 for c in cands if c["symptom_scores"].get(top, 0) > 0)
            hit_den += len(cands)

    pairs = [jaccard(sets[i], sets[j])
             for i in range(len(sets)) for j in range(i + 1, len(sets))]
    return {
        "coverage": len(appear) / max(len(store), 1),
        "jaccard": sum(pairs) / len(pairs) if pairs else 0.0,
        "hit_rate": hit_num / hit_den if hit_den else 0.0,
        "avg_candidates": sum(sizes) / len(sizes) if sizes else 0,
        "top_product": appear.most_common(1)[0] if appear else (None, 0),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="auto", choices=["auto", "st", "hashing"])
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--csv", default=str(PRODUCTS_CSV))
    args = ap.parse_args(argv)

    df = pd.read_csv(args.csv, encoding="utf-8-sig")
    scenarios = sample_scenarios(args.n)
    print(f"상품 {len(df)}개 / 시나리오 {len(scenarios)}개\n")

    print(f"{'Document 구성':22s} {'커버리지':>8s} {'자카드':>8s} {'주증상 적중':>10s} {'문장 길이':>9s}")
    print("-" * 64)
    for label, parts in VARIANTS.items():
        embedder = get_embedder(args.backend)       # 변형마다 새로 fit 하도록 분리
        store, texts = build_store(df, parts, embedder)
        m = run(store, embedder, scenarios)
        avg_len = sum(len(t) for t in texts) // len(texts)
        print(f"{label:22s} {m['coverage']:7.1%} {m['jaccard']:8.3f} "
              f"{m['hit_rate']:9.1%} {avg_len:8d}자")

    print("\n해석 기준")
    print("  커버리지   높을수록 좋다. 소수 상품이 모든 사용자에게 반복되지 않는다는 뜻")
    print("  자카드     낮을수록 좋다. 증상이 다르면 후보도 달라진다는 뜻")
    print("  주증상 적중 높을수록 좋다. 가장 심한 증상에 성분 근거가 있는 상품을 데려온다는 뜻")
    print("\n커버리지와 적중률이 같이 올라가는 구성을 고른다.")
    print("적중률만 올라가고 커버리지가 떨어지면 성분 점수 높은 상품만 반복해서 뽑는 상태다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
