# 수집한 원본 CSV -> 추천에 쓸 data/products.csv

# 1. 열 확인, 공백 정리
# 2. 상품 링크(goodsNo) 기준 중복 제거
# 3. 상품명 정리 (대괄호 홍보 문구, 용량, 기획/증정 표기 제거)
# 4. 성분 문자열 정리 (@ 구분자, "리뉴얼 후" 같은 머리말, 줄바꿈)
# 5. 숫자 열 변환 (가격, 별점, 리뷰 수)
# 6. 카테고리 검사
# 7. 쓸 수 없는 행 제외 (성분 없음, 가격 없음)

# 실행 python prepare_data.py raw.csv


import re
import sys
from pathlib import Path

import pandas as pd

OUT = Path("data/products.csv")
VALID_CATEGORIES = {"shampoo", "scaler", "tonic", "treatment"}
NEEDED = ["name", "volume", "spec", "ingredients", "link",
          "price", "rating", "reviews", "image", "category"]


def clean_name(name: str) -> str:
    n = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", str(name))
    n = re.sub(r"\d+(\.\d+)?\s*(ml|ML|mL|g|G|L|매|개입|개)", " ", n)
    n = re.sub(r"(기획|단품|대용량|증정|더블|리필|세트|택\s*1|\d+\s*종|NEW|new)", " ", n)
    n = re.sub(r"[+＋*/]\s*$", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def clean_ingredients(ing: str) -> str:
    s = str(ing)
    s = s.replace("@", ", ")                                   # 일부 상품이 @ 로 구분
    s = re.sub(r"^\s*\*?\s*리뉴얼\s*(전|후)\s*", "", s)          # 머리말 제거
    s = re.sub(r"\[ILN\d+\].*$", "", s)                        # 코드 표기 제거
    s = re.sub(r"\*+\s*제공된 성분.*$", "", s)                   # 안내 문구 제거
    s = s.replace("\n", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def goods_key(url: str) -> str:
    u = str(url)
    m = re.search(r"goodsNo=(\w+)", u) or re.search(r"/goods/(?:[^/?]*/)?(\d+)", u)
    return m.group(1) if m else u.split("?")[0]


def main(src: str):
    df = pd.read_csv(src, encoding="utf-8-sig")
    start = len(df)
    log = []

    missing = [c for c in NEEDED if c not in df.columns]
    if missing:
        print(f"열이 없습니다: {missing}")
        return

    # 공백 정리
    for c in ["name", "volume", "spec", "link", "image", "category"]:
        df[c] = df[c].astype(str).str.strip().replace({"nan": ""})

    # 중복 제거
    df["_key"] = df["link"].apply(goods_key)
    dup = df.duplicated("_key").sum()
    df = df.drop_duplicates("_key").reset_index(drop=True)
    log.append(f"링크 중복 제거: {dup}개")

    # 정리
    df["name_clean"] = df["name"].apply(clean_name)
    df["ingredients"] = df["ingredients"].apply(clean_ingredients)

    dup2 = df.duplicated("name_clean").sum()
    if dup2:
        log.append(f"이름 중복(용량만 다른 제품) 의심: {dup2}개 - 확인 필요")
        for n in df[df.duplicated("name_clean", keep=False)]["name"].tolist():
            log.append(f"    {n[:60]}")

    # 숫자 변환
    df["price"] = pd.to_numeric(df["price"].astype(str).str.replace(r"[^\d]", "", regex=True),
                                errors="coerce")
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    df["reviews"] = pd.to_numeric(df["reviews"].astype(str).str.replace(r"[^\d]", "", regex=True),
                                  errors="coerce").fillna(0).astype(int)

    # 카테고리 검사
    bad = df[~df["category"].isin(VALID_CATEGORIES)]
    if len(bad):
        log.append(f"카테고리 이상 {len(bad)}개 - 제외")
        for _, r in bad.iterrows():
            log.append(f"    {r['name'][:50]} -> '{r['category']}'")
        df = df[df["category"].isin(VALID_CATEGORIES)]

    # 쓸 수 없는 행 제외
    no_ing = df["ingredients"].str.len() < 20
    if no_ing.sum():
        log.append(f"성분 없음 {int(no_ing.sum())}개 - 제외")
        for n in df[no_ing]["name"]: log.append(f"    {n[:50]}")
        df = df[~no_ing]

    no_price = df["price"].isna()
    if no_price.sum():
        log.append(f"가격 없음 {int(no_price.sum())}개 - 제외")
        df = df[~no_price]

    df["price"] = df["price"].astype(int)

    # 평점 비어 있는 행은 남김 (추천 코드에서 평균으로 보정)
    n_norating = int(df["rating"].isna().sum())
    if n_norating:
        log.append(f"별점 없음 {n_norating}개 - 유지 (보정 평점 사용)")

    OUT.parent.mkdir(exist_ok=True)
    df.drop(columns=["_key"]).to_csv(OUT, index=False, encoding="utf-8-sig")

    print("\n".join(log))
    print(f"\n{start}개 -> {len(df)}개 저장: {OUT}")
    print("\n[카테고리별]")
    print(df["category"].value_counts().to_string())
    print(f"\n가격 {df.price.min():,} ~ {df.price.max():,}원 (중앙값 {int(df.price.median()):,})")
    print(f"성분 개수 평균 {int(df.ingredients.str.count(',').mean())}개")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "raw.csv")