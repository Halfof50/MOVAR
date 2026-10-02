"""
상품 → 검색용 Document

상품명만 임베딩하면 변별이 되지 않는다.
데이터셋의 샴푸 83개가 대부분 "○○ 두피 샴푸" 형태라 벡터가 서로 가깝게 몰린다.

spec 열도 그대로 쓸 수 없다.
146개 중 138개가 20자 미만이고 "모든 피부용", "모든 모발용" 같은 문구다.
설명으로서 의미가 없는 값이 대다수라 20자 이상일 때만 넣는다.

그래서 Document 는 네 가지로 구성한다.
    상품명 / 카테고리 / 검출된 유효 성분 / 성분 점수에서 도출한 관리 목적

유효 성분 조합은 제품마다 다르므로 이 줄이 실제 변별력을 만든다.

가격·평점·리뷰·링크·이미지·전체 전성분은 임베딩에 넣지 않는다.
의미 검색 대상이 아니고, 필터링과 재정렬 단계에서 쓴다.
"""

import re

from recommendation.config import CATEGORY_KR, DOC_PARTS, SYMPTOMS, SYMPTOM_KR
from recommendation.preprocessing.ingredient_scores import (
    ingredient_scores, active_ingredients,
)

# 증상 → 검색 문맥에서 쓸 관리 목적 표현
CARE_PURPOSE = {
    "micro_keratin":       "두피 각질 관리",
    "excess_sebum":        "피지 유분 관리",
    "follicular_erythema": "붉어진 두피 진정",
    "follicular_pustule":  "두피 트러블 관리",
    "dandruff":            "비듬 관리",
    "hair_loss":           "탈모 증상 완화 관리",
}

SPEC_MIN_LEN = 20          # 이 길이 미만의 spec 은 설명으로 보지 않는다
PURPOSE_MAX  = 3           # 관리 목적은 점수 높은 순으로 최대 3개


def extract_brand(name_clean: str) -> str:
    """정제된 상품명의 첫 토큰을 브랜드로 본다.

    별도 브랜드 열이 없어서 쓰는 근사값이다.
    원본 name 은 '[9월 올영픽]' 같은 홍보 문구가 앞에 붙어 쓸 수 없고,
    name_clean 의 첫 토큰은 데이터셋에서 79종으로 나뉘어 브랜드 구분에 쓸 수 있다.
    """
    s = re.sub(r"[\[\]()]", " ", str(name_clean or "")).strip()
    tokens = s.split()
    return tokens[0] if tokens else ""


def build_document(row, parts=None) -> str:
    """상품 한 행 → 임베딩에 넣을 텍스트

    parts 로 넣을 줄을 고를 수 있다. 기본값은 config.DOC_PARTS.
    어느 줄이 검색에 실제로 기여하는지 비교하려고 토글로 뒀다.

    측정해 둔 값 (상품 146개 기준)
      - 상품명만으로도 Document 146개가 전부 다르다. '문장이 서로 다르다'는
        변별력의 근거가 되지 못한다.
      - 유효성분 조합은 98종. 유효성분이 검출되지 않은 상품 15개는 이 줄이 비어 있다.
      - 관리 목적은 26종뿐이고 상위 1개 조합에 29개 상품이 몰린다.
      - 살리실릭애씨드 67%, 멘톨 57% 는 대다수 상품에 들어 있어
        상품을 가르는 쪽이 아니라 붙이는 쪽으로 작용한다.
      - 관리 목적은 성분 점수에서 도출한 값이므로, 이 줄을 넣으면
        임베딩 유사도가 성분 점수와 같은 방향으로 움직인다.
        '성분 규칙에 걸리지 않는 제품을 임베딩으로 보완한다'는 목적과 상충한다.
    """
    use = parts if parts is not None else DOC_PARTS
    scores, _ = ingredient_scores(row.get("ingredients", ""))
    actives = active_ingredients(row.get("ingredients", ""))
    lines = []

    if "name" in use:
        lines.append(f"상품명: {row.get('name_clean') or row.get('name')}")
    if "category" in use:
        lines.append(f"카테고리: {CATEGORY_KR.get(row.get('category'), row.get('category'))}")

    spec = str(row.get("spec") or "").strip()
    if "spec" in use and len(spec) >= SPEC_MIN_LEN:
        lines.append(f"제품 설명: {spec}")

    if "actives" in use and actives:
        lines.append(f"주요 유효성분: {', '.join(actives)}")

    if "purpose" in use:
        ranked = [s for s in sorted(SYMPTOMS, key=lambda x: -scores[x]) if scores[s] > 0]
        if ranked:
            purposes = [CARE_PURPOSE[s] for s in ranked[:PURPOSE_MAX]]
            lines.append(f"관리 목적: {', '.join(purposes)}")

    if not lines:                       # 모든 줄을 끄면 상품명만 남긴다
        lines = [str(row.get("name_clean") or row.get("name"))]
    return "\n".join(lines)


def build_record(row, product_id, parts=None) -> dict:
    """상품 한 행 → 인덱스에 저장할 레코드

    embed_text 는 벡터로 변환되고, 나머지는 메타데이터로 보관된다.

    성분 점수와 유효 성분은 저장하지 않는다.
    상품을 추천할 때마다 후보에 대해 다시 계산한다 (retriever 가 한다).
    점수표가 바뀌어도 인덱스를 다시 만들 필요가 없고,
    저장된 점수와 실제 점수표가 어긋나는 일도 생기지 않는다.

    전체 전성분은 반드시 그대로 남긴다. 모든 재계산의 원본이다.
    """
    return {
        "product_id":   int(product_id),
        "name":         row.get("name"),
        "name_clean":   row.get("name_clean"),
        "brand":        extract_brand(row.get("name_clean") or row.get("name")),
        "category":     row.get("category"),
        "volume":       row.get("volume"),
        "spec":         row.get("spec"),
        "price":        _int(row.get("price")),
        "rating":       _float(row.get("rating")),
        "reviews":      _int(row.get("reviews")),
        "link":         row.get("link"),
        "image":        row.get("image"),
        "ingredients":  row.get("ingredients"),
        "embed_text":   build_document(row, parts),
    }


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _float(v):
    try:
        f = float(v)
        return None if f != f else f          # NaN 제외
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    import pandas as pd
    from recommendation.config import PRODUCTS_CSV

    df = pd.read_csv(PRODUCTS_CSV, encoding="utf-8-sig")
    docs = [build_document(r) for _, r in df.iterrows()]

    print("=== 예시 3건 ===")
    for d in docs[:3]:
        print(d)
        print("-" * 50)

    lens = [len(d) for d in docs]
    print(f"Document 길이  평균 {sum(lens)//len(lens)}자  최소 {min(lens)}  최대 {max(lens)}")
    print(f"서로 다른 Document: {len(set(docs))} / {len(docs)}")
    print(f"유효성분 줄이 없는 상품: {sum('주요 유효성분' not in d for d in docs)}")
    print(f"제품 설명 줄이 들어간 상품: {sum('제품 설명' in d for d in docs)}")
