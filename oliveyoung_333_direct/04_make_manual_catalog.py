import pandas as pd

import config
from common import clean_text


CATEGORY_PRIORITY = [
    "탈모증상완화",
    "지성/피지/딥클렌징",
    "건성/보습",
    "민감/저자극/약산성",
    "비듬/각질",
    "손상모/일반",
]


def first_category(tags, mfds_status):
    if (
        clean_text(mfds_status)
        .upper()
        == "MATCHED"
    ):
        return "탈모증상완화"

    tag_list = [
        x.strip()
        for x in clean_text(
            tags
        ).split(";")
        if x.strip()
    ]

    for category in CATEGORY_PRIORITY:
        if category in tag_list:
            return category

    return "손상모/일반"


def existing_manual():
    if not config.MANUAL_CSV.exists():
        return {}

    old = pd.read_csv(
        config.MANUAL_CSV,
        encoding="utf-8-sig",
    )

    keep = {}

    for _, row in old.iterrows():
        goods_no = clean_text(
            row.get(
                "OLIVEYOUNG_GOODS_NO",
                "",
            )
        )

        if not goods_no:
            continue

        keep[goods_no] = {
            "RAW_INGREDIENTS": clean_text(
                row.get(
                    "RAW_INGREDIENTS",
                    "",
                )
            ),
            "INGREDIENT_SOURCE_URL": clean_text(
                row.get(
                    "INGREDIENT_SOURCE_URL",
                    "",
                )
            ),
            "INGREDIENT_STATUS": clean_text(
                row.get(
                    "INGREDIENT_STATUS",
                    "",
                )
            ) or "TODO",
            "NOTE": clean_text(
                row.get(
                    "NOTE",
                    "",
                )
            ),
        }

    return keep


def main():
    df = pd.read_csv(
        config.MFDS_MATCHED_CSV,
        encoding="utf-8-sig",
    )

    old = existing_manual()
    rows = []

    for _, row in df.iterrows():
        goods_no = clean_text(
            row.get(
                "OLIVEYOUNG_GOODS_NO",
                "",
            )
        )

        item = {
            "ROW_NO": 0,
            "CATEGORY_PRIMARY": first_category(
                row.get(
                    "CATEGORY_TAGS",
                    "",
                ),
                row.get(
                    "MFDS_MATCH_STATUS",
                    "",
                ),
            ),
            "CATEGORY_TAGS": clean_text(
                row.get(
                    "CATEGORY_TAGS",
                    "",
                )
            ),
            "PRODUCT_NAME": clean_text(
                row.get(
                    "PRODUCT_NAME",
                    "",
                )
            ),
            "BRAND_NAME": clean_text(
                row.get(
                    "BRAND_NAME",
                    "",
                )
            ),
            "OLIVEYOUNG_GOODS_NO": goods_no,
            "PRODUCT_URL": clean_text(
                row.get(
                    "PRODUCT_URL",
                    "",
                )
            ),
            "MFDS_MATCH_STATUS": clean_text(
                row.get(
                    "MFDS_MATCH_STATUS",
                    "",
                )
            ),
            "MFDS_CANDIDATE_PRODUCT_NAME": clean_text(
                row.get(
                    "MFDS_CANDIDATE_PRODUCT_NAME",
                    "",
                )
            ),
            "MFDS_MATCH_SCORE": row.get(
                "MFDS_MATCH_SCORE",
                "",
            ),
            # 핵심: 전성분표 전체를 한 셀에 그대로 복붙
            "RAW_INGREDIENTS": "",
            "INGREDIENT_SOURCE_URL": "",
            "INGREDIENT_STATUS": "TODO",
            "NOTE": "",
        }

        # 재실행해도 사람이 입력한 전성분은 보존
        if goods_no in old:
            item.update(
                old[goods_no]
            )

        rows.append(
            item
        )

    for i, item in enumerate(
        rows,
        start=1,
    ):
        item["ROW_NO"] = i

    out = pd.DataFrame(
        rows
    )

    out.to_csv(
        config.MANUAL_CSV,
        index=False,
        encoding="utf-8-sig",
    )

    print(
        "저장:",
        config.MANUAL_CSV,
    )
    print(
        "수동 전성분 입력 대상:",
        len(out),
        "개",
    )
    print(
        "RAW_INGREDIENTS 열에 전성분 전체를 그대로 복붙하세요."
    )


if __name__ == "__main__":
    main()
