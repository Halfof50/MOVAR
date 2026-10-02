"""
상품 인덱스 생성

    python -m recommendation.build_index
    python -m recommendation.build_index --backend hashing    # 배선 점검용

하는 일
    CSV 읽기
      → 성분명 정규화
      → 증상별 성분 점수
      → 유효 성분 추출
      → 알레르기 파생 정보
      → 검색용 Document 생성
      → 임베딩
      → data/index/ 에 저장

상품이 추가되면 이 스크립트만 다시 돌린다. 모델은 다시 학습하지 않는다.
"""

import argparse
import sys

import pandas as pd

from recommendation.config import INDEX_DIR, PRODUCTS_CSV
from recommendation.embedding.embedding_model import get_embedder
from recommendation.embedding.vector_store import VectorStore
from recommendation.preprocessing.product_document import build_record


def load_products(csv_path=PRODUCTS_CSV) -> pd.DataFrame:
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    need = {"name", "category", "ingredients"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"CSV 에 필요한 열이 없습니다: {sorted(missing)}")
    return df


def build_records(df: pd.DataFrame) -> list:
    # 알레르기 파생 정보는 넣지 않는다.
    # 별도 모듈(Allergy RAG)로 분리할 예정이고, 그전까지는 추천 경로에서 뺀다.
    return [build_record(row, product_id=i + 1) for i, row in df.iterrows()]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(PRODUCTS_CSV))
    ap.add_argument("--out", default=str(INDEX_DIR))
    ap.add_argument("--backend", default="auto", choices=["auto", "st", "hashing"])
    args = ap.parse_args(argv)

    df = load_products(args.csv)
    print(f"상품 {len(df)}개 읽음: {args.csv}")

    records = build_records(df)
    texts = [r["embed_text"] for r in records]
    print(f"Document 생성 완료. 서로 다른 Document {len(set(texts))}개")

    embedder = get_embedder(args.backend)
    if getattr(embedder, "requires_fit", False):
        embedder.fit(texts)
        print("※ 테스트 백엔드로 생성했습니다. 검색 품질 평가에는 쓸 수 없습니다.")

    vectors = embedder.encode(texts)
    print(f"임베딩 완료: {vectors.shape}  모델 {embedder.name}")

    store = VectorStore.build(records, vectors, embedder.name)
    out = store.save(args.out)
    print(f"저장 완료: {out}")

    # 간단한 점검
    from recommendation.preprocessing.ingredient_scores import ingredient_scores
    n_zero = sum(1 for r in records
                 if not any(ingredient_scores(r["ingredients"])[0].values()))
    print(f"\n성분 점수가 전부 0인 상품 {n_zero}개")
    print("카테고리별", df["category"].value_counts().to_dict())
    return 0


if __name__ == "__main__":
    sys.exit(main())
