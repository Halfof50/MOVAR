"""
벡터 저장소

구성
    vectors.npy    (N, dim) float32, L2 정규화된 상품 벡터
    records.json   상품 메타데이터 (전체 전성분 포함)
    meta.json      모델 이름, 차원, 상품 수, 생성 시각

검색은 정확 탐색(내적)으로 한다. 근사 탐색(IVF, HNSW)을 쓰지 않는 이유는 두 가지다.
 1. 조건 필터를 먼저 적용한 뒤 그 부분집합만 비교하면 결과가 항상 정확하다.
    근사 탐색은 필터가 좁을 때 요청한 개수보다 적게 돌려주는 문제가 있다.
 2. 학습이 필요한 인덱스(IVF)는 상품이 늘 때마다 다시 학습해야 한다.

정확 탐색의 비용은 (상품 수 × 차원) 곱셈 한 번이다.
상품이 수만 건 규모가 되어 이 비용이 문제가 되면 FAISS HNSW 로 교체한다.
그때도 저장 형식과 search() 호출부는 그대로 두고 내부만 바꾸면 된다.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from recommendation.config import INDEX_DIR


class VectorStore:

    def __init__(self, vectors=None, records=None, meta=None):
        self.vectors = None if vectors is None else np.asarray(vectors, dtype="float32")
        self.records = records or []
        self.meta = meta or {}
        self._id_pos = None

    # ── 생성 / 저장 / 로드 ──────────────────────────────

    @classmethod
    def build(cls, records, vectors, model_name: str):
        if len(records) != len(vectors):
            raise ValueError(f"레코드 {len(records)}개와 벡터 {len(vectors)}개가 맞지 않습니다.")
        v = np.asarray(vectors, dtype="float32")
        meta = {
            "model": model_name,
            "dim": int(v.shape[1]),
            "count": int(v.shape[0]),
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        return cls(v, list(records), meta)

    def save(self, index_dir=INDEX_DIR):
        d = Path(index_dir)
        d.mkdir(parents=True, exist_ok=True)
        np.save(d / "vectors.npy", self.vectors)
        (d / "records.json").write_text(
            json.dumps(self.records, ensure_ascii=False, indent=1), encoding="utf-8")
        (d / "meta.json").write_text(
            json.dumps(self.meta, ensure_ascii=False, indent=1), encoding="utf-8")
        return d

    @classmethod
    def load(cls, index_dir=INDEX_DIR):
        d = Path(index_dir)
        if not (d / "vectors.npy").exists():
            raise FileNotFoundError(
                f"인덱스가 없습니다: {d}\n먼저 python -m recommendation.build_index 를 실행하십시오.")
        vectors = np.load(d / "vectors.npy")
        records = json.loads((d / "records.json").read_text(encoding="utf-8"))
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        return cls(vectors, records, meta)

    def __len__(self):
        return 0 if self.vectors is None else int(self.vectors.shape[0])

    def vector_of(self, product_id):
        """product_id → 벡터. 재정렬 단계에서 후보끼리 비교할 때 쓴다."""
        if self._id_pos is None:
            self._id_pos = {r.get("product_id"): i for i, r in enumerate(self.records)}
        i = self._id_pos.get(product_id)
        return None if i is None else self.vectors[i]

    # ── 검색 ────────────────────────────────────────────

    def _mask(self, category=None, max_price=None, min_price=None,
              exclude_ids=None):
        n = len(self)
        keep = np.ones(n, dtype=bool)
        exclude_ids = set(exclude_ids or [])

        for i, r in enumerate(self.records):
            if category and r.get("category") != category:
                keep[i] = False; continue
            if r.get("product_id") in exclude_ids:
                keep[i] = False; continue
            price = r.get("price")
            if max_price is not None and (price is None or price > max_price):
                keep[i] = False; continue
            if min_price is not None and (price is None or price < min_price):
                keep[i] = False; continue
        return keep

    def search(self, query_vector, top_k=15, **filters):
        """
        조건에 맞는 상품 중 유사도 상위 top_k 개를 반환한다.
        반환 항목은 레코드 복사본 + similarity + retrieval_rank.
        """
        if len(self) == 0:
            return []

        q = np.asarray(query_vector, dtype="float32").reshape(-1)
        keep = self._mask(**filters)
        idx = np.flatnonzero(keep)
        if idx.size == 0:
            return []

        sims = self.vectors[idx] @ q
        k = min(top_k, idx.size)
        order = np.argpartition(-sims, k - 1)[:k]
        order = order[np.argsort(-sims[order])]

        out = []
        for rank, o in enumerate(order, start=1):
            rec = dict(self.records[idx[o]])
            rec["similarity"] = round(float(sims[o]), 4)
            rec["retrieval_rank"] = rank
            out.append(rec)
        return out

    def search_by_category(self, query_vectors: dict, quota: dict, **filters):
        """
        카테고리별로 할당량만큼 따로 검색해 합친다.

        전체에서 상위 K개만 뽑으면 한 카테고리로 쏠려
        '샴푸 + 스케일러' 같은 조합을 만들 수 없는 경우가 생긴다.
        카테고리별 Query 를 따로 넣을 수 있게 dict 로 받는다.
        """
        merged = []
        for cat, k in quota.items():
            if k <= 0:
                continue
            qv = query_vectors.get(cat) if isinstance(query_vectors, dict) else query_vectors
            if qv is None:
                continue
            merged.extend(self.search(qv, top_k=k, category=cat, **filters))

        merged.sort(key=lambda r: -r["similarity"])
        for i, r in enumerate(merged, start=1):
            r["retrieval_rank"] = i
        return merged


if __name__ == "__main__":
    store = VectorStore.load()
    print("meta:", store.meta)
    print("상품 수:", len(store))
    print("첫 레코드 키:", sorted(store.records[0].keys()))
