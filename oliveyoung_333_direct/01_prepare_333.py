import pandas as pd

import config
from common import clean_text


def brand_from_anchor(anchor):
    anchor = clean_text(anchor)
    if not anchor:
        return ""

    # Edge 카테고리 DOM에서 ANCHOR_TEXT의 첫 토큰이 브랜드명인 형태를 사용.
    # 예: "라보에이치 [4년연속1위] NEW라보에이치 ..." -> "라보에이치"
    return anchor.split(" ", 1)[0]


def main():
    df = pd.read_csv(
        config.OLIVEYOUNG_CSV,
        encoding="utf-8-sig",
    )

    required = {
        "OLIVEYOUNG_GOODS_NO",
        "PRODUCT_URL",
        "ANCHOR_TEXT",
        "CARD_TEXT",
    }

    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"필수 열이 없습니다: {sorted(missing)}"
        )

    # 이미 병합한 333개 파일이므로 여기서 다시 페이지 병합하지 않는다.
    df = df.drop_duplicates(
        subset=["OLIVEYOUNG_GOODS_NO"],
        keep="first",
    ).copy()

    df = df[
        df["OLIVEYOUNG_GOODS_NO"]
        .astype(str)
        .str.match(r"^A\d{12}$")
    ].copy()

    df = df[
        df["OLIVEYOUNG_GOODS_NO"] != "A000000000000"
    ].copy()

    # 중요:
    # PRODUCT_NAME은 가격/세일 문구까지 붙는 CARD_TEXT가 아니라
    # Edge에서 이미 깔끔하게 받은 ANCHOR_TEXT를 그대로 사용.
    df["LISTING_TITLE"] = (
        df["ANCHOR_TEXT"]
        .fillna("")
        .astype(str)
        .map(clean_text)
    )

    df["PRODUCT_NAME"] = df["LISTING_TITLE"]
    df["BRAND_NAME"] = df["LISTING_TITLE"].map(
        brand_from_anchor
    )

    # 사람이 나중에 채울 열
    df["RAW_INGREDIENTS"] = ""
    df["INGREDIENT_SOURCE_URL"] = ""
    df["INGREDIENT_STATUS"] = "TODO"

    cols = [
        "OLIVEYOUNG_GOODS_NO",
        "PRODUCT_NAME",
        "BRAND_NAME",
        "PRODUCT_URL",
        "LISTING_TITLE",
        "ANCHOR_TEXT",
        "CARD_TEXT",
        "RAW_INGREDIENTS",
        "INGREDIENT_SOURCE_URL",
        "INGREDIENT_STATUS",
    ]

    df[cols].to_csv(
        config.PREPARED_CSV,
        index=False,
        encoding="utf-8-sig",
    )

    print("입력 행:", len(pd.read_csv(config.OLIVEYOUNG_CSV, encoding='utf-8-sig')))
    print("고유 상품:", len(df))
    print("저장:", config.PREPARED_CSV)


if __name__ == "__main__":
    main()
