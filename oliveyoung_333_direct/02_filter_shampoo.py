import pandas as pd

import config
from common import clean_text


NEGATIVE = [
    "드라이샴푸",
    "드라이 샴푸",
    "미스트",
    "토닉",
    "세럼",
    "앰플",
    "에센스",
    "트리트먼트",
    "컨디셔너",
    "린스",
    "헤어팩",
    "오일",
]

CATEGORY_KEYWORDS = {
    "탈모증상완화": [
        "탈모",
        "두피강화",
        "폴리젠",
        "헤어리프팅",
        "안티헤어로스",
    ],
    "지성/피지/딥클렌징": [
        "지성",
        "피지",
        "딥클린",
        "딥 클린",
        "쿨링",
        "노세범",
        "퓨리파잉",
        "퍼리파잉",
        "스케일링",
        "클렌징",
        "청정",
    ],
    "건성/보습": [
        "건성",
        "보습",
        "수분",
        "모이스처",
        "모이스트",
        "하이드라",
        "하이드레이팅",
        "촉촉",
    ],
    "민감/저자극/약산성": [
        "민감",
        "저자극",
        "약산성",
        "마일드",
        "시카",
        "센서티브",
        "피에이치",
        "ph",
    ],
    "비듬/각질": [
        "비듬",
        "각질",
        "댄드러프",
        "안티댄드러프",
        "안티-댄드러프",
    ],
    "손상모/일반": [
        "손상",
        "극손상",
        "리페어",
        "단백질",
        "펩타이드",
        "퍼퓸",
        "영양",
        "케라틴",
        "데미지",
    ],
}


def combined_text(row):
    return " ".join([
        clean_text(row.get("PRODUCT_NAME", "")),
        clean_text(row.get("CARD_TEXT", "")),
    ]).lower()


def is_shampoo(row):
    text = combined_text(row)

    if "샴푸" not in text and "shampoo" not in text:
        return False

    if any(word.lower() in text for word in NEGATIVE):
        return False

    return True


def category_tags(row):
    text = combined_text(row)
    tags = []

    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(k.lower() in text for k in keywords):
            tags.append(category)

    if is_shampoo(row) and not tags:
        tags.append("손상모/일반")

    return ";".join(tags)


def main():
    df = pd.read_csv(
        config.PREPARED_CSV,
        encoding="utf-8-sig",
    )

    df["IS_SHAMPOO"] = df.apply(
        is_shampoo,
        axis=1,
    )

    df["CATEGORY_TAGS"] = df.apply(
        category_tags,
        axis=1,
    )

    df.to_csv(
        config.ALL_CLASSIFIED_CSV,
        index=False,
        encoding="utf-8-sig",
    )

    shampoo = df[
        df["IS_SHAMPOO"] == True
    ].copy()

    shampoo.to_csv(
        config.SHAMPOO_ONLY_CSV,
        index=False,
        encoding="utf-8-sig",
    )

    print("올리브영 전체:", len(df))
    print("실제 샴푸:", len(shampoo))
    print("제외 상품:", len(df) - len(shampoo))
    print("전체:", config.ALL_CLASSIFIED_CSV)
    print("샴푸:", config.SHAMPOO_ONLY_CSV)


if __name__ == "__main__":
    main()
