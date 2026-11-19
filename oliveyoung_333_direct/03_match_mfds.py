import re

import pandas as pd
from rapidfuzz import fuzz

import config
from common import clean_text, normalize_text


MARKETING_WORDS = [
    "탈모증상완화",
    "탈모증상의완화",
    "탈모완화",
    "기능성",
    "올영단독",
    "올영픽",
    "단독",
    "기획",
    "더블",
    "듀오",
    "세트",
    "증정",
    "대용량",
    "리뉴얼",
    "new",
    "한정",
    "택1",
    "택 1",
    "단품",
    "리필",
    "콜라보",
    "베스트",
    "오특",
]

GENERIC_WORDS = [
    "샴푸액",
    "샴푸",
    "shampoo",
    "탈모증상완화",
    "탈모증상의완화",
    "탈모완화",
    "기능성",
]

GENERIC_CORES = {
    "",
    "탈모",
    "두피",
    "헤어",
    "모발",
}


def strip_noise(value):
    text = clean_text(value).lower()

    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = re.sub(
        r"\([^\)]*(?:증정|기획|세트|택|단품|리필)[^\)]*\)",
        " ",
        text,
    )
    text = re.sub(
        r"\b\d+(?:\.\d+)?\s*(?:ml|g|kg|l)\b",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\+\s*\d+(?:\.\d+)?\s*(?:ml|g|l)?",
        " ",
        text,
        flags=re.I,
    )

    for word in MARKETING_WORDS:
        text = text.replace(word, " ")

    return normalize_text(text)


def core_name(value, mfds=False):
    text = strip_noise(value)

    if mfds:
        text = re.sub(
            r"^(?:19|20)\d{2}",
            "",
            text,
        )

    for word in GENERIC_WORDS:
        text = text.replace(word, "")

    text = re.sub(
        r"\d+(?:입|종)$",
        "",
        text,
    )

    return text


def usable_core(value):
    return (
        bool(value)
        and value not in GENERIC_CORES
        and len(value) >= 4
    )


def pair_score(a, b):
    if not a or not b:
        return 0.0

    if a == b:
        return 100.0

    score = fuzz.ratio(a, b)
    lr = min(len(a), len(b)) / max(len(a), len(b))

    if lr >= 0.72:
        score = max(
            score,
            fuzz.WRatio(a, b),
        )

    if (
        (a in b or b in a)
        and min(len(a), len(b)) >= 6
        and lr >= 0.72
    ):
        score = max(
            score,
            96.0,
        )

    return round(score, 3)


def main():
    retail = pd.read_csv(
        config.SHAMPOO_ONLY_CSV,
        encoding="utf-8-sig",
    )

    mfds = pd.read_csv(
        config.MFDS_CSV,
        encoding="utf-8-sig",
    )

    mfds["_CORE"] = mfds[
        "PRODUCT_NAME"
    ].apply(
        lambda x: core_name(
            x,
            mfds=True,
        )
    )

    mfds = mfds[
        mfds["_CORE"].apply(
            usable_core
        )
    ].copy()

    results = []

    for n, (_, row) in enumerate(
        retail.iterrows(),
        start=1,
    ):
        retail_core = core_name(
            row.get(
                "PRODUCT_NAME",
                "",
            )
        )

        scores = []

        for idx, candidate in mfds.iterrows():
            s = pair_score(
                retail_core,
                candidate["_CORE"],
            )
            scores.append(
                (s, idx)
            )

        scores.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        best_score = (
            scores[0][0]
            if scores
            else 0.0
        )
        best_idx = (
            scores[0][1]
            if scores
            else None
        )
        second_score = (
            scores[1][0]
            if len(scores) > 1
            else 0.0
        )

        gap = (
            best_score
            - second_score
        )

        item = row.to_dict()

        item["MFDS_MATCH_SCORE"] = round(
            best_score,
            2,
        )
        item["MFDS_SECOND_SCORE"] = round(
            second_score,
            2,
        )
        item["MFDS_SCORE_GAP"] = round(
            gap,
            2,
        )

        if best_idx is not None:
            best = mfds.loc[
                best_idx
            ]
            item[
                "MFDS_CANDIDATE_PRODUCT_NAME"
            ] = best.get(
                "PRODUCT_NAME",
                "",
            )
            item[
                "MFDS_CANDIDATE_COMPANY_NAME"
            ] = best.get(
                "COMPANY_NAME",
                "",
            )

        if (
            best_score >= 93
            and gap >= 5
        ):
            status = "MATCHED"
        elif (
            best_score >= 80
            and gap >= 5
        ):
            status = "REVIEW"
        else:
            status = "NOT_MATCHED"

        item[
            "MFDS_MATCH_STATUS"
        ] = status

        results.append(
            item
        )

        print(
            f"[{n}/{len(retail)}] "
            f"{row.get('PRODUCT_NAME','')} -> "
            f"{item.get('MFDS_CANDIDATE_PRODUCT_NAME','')} "
            f"({best_score:.1f}, gap={gap:.1f}) "
            f"{status}"
        )

    out = pd.DataFrame(
        results
    )

    out.to_csv(
        config.MFDS_MATCHED_CSV,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print(
        "저장:",
        config.MFDS_MATCHED_CSV,
    )
    print(
        out[
            "MFDS_MATCH_STATUS"
        ].value_counts(
            dropna=False
        )
    )


if __name__ == "__main__":
    main()
