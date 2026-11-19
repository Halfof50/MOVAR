import re
import pandas as pd

import config
from common import clean_text, normalize_text


INGREDIENT_SPLITTER = re.compile(r"\s*[,，;]\s*")
BRACKET_MARKER = re.compile(r"\[([^\[\]]+)\]")
BULLET = "■"


def split_ingredients(raw):
    raw = clean_text(raw)

    if not raw:
        return []

    result = []

    for part in INGREDIENT_SPLITTER.split(raw):
        part = clean_text(part).strip("·ㆍ|/")

        if part:
            result.append(part)

    return result


def parse_formula_version(label):
    label = clean_text(label)

    if not label:
        return "", None

    if label.startswith("리뉴얼"):
        name = clean_text(label[len("리뉴얼"):])
        return name or "기본", "RENEWAL"

    return label, None


def parse_bracket_variants(raw):
    """
    [오스만투스] 정제수, ...
    [히노키] 정제수, ...
    """
    matches = list(BRACKET_MARKER.finditer(raw))

    if not matches:
        return []

    blocks = []

    for i, match in enumerate(matches):
        label = clean_text(match.group(1))

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)

        ingredients_text = clean_text(raw[start:end])

        ingredients_text = re.sub(
            r"^\s*[-–—:]\s*",
            "",
            ingredients_text,
        )

        variant_name, version = parse_formula_version(label)

        blocks.append({
            "variant_name": variant_name or "기본",
            "formula_version": version,
            "raw_ingredients": ingredients_text,
            "parse_style": "BRACKET",
            "parse_status": "OK" if ingredients_text else "EMPTY",
        })

    has_renewal = any(
        b["formula_version"] == "RENEWAL"
        for b in blocks
    )

    for block in blocks:
        if block["formula_version"] is None:
            block["formula_version"] = (
                "ORIGINAL"
                if has_renewal
                else "CURRENT"
            )

    return blocks


def parse_bullet_chunk(chunk):
    """
    지원:
    ■가려운두피케어- 정제수, ...
    ■리뉴얼 가려운두피케어 정제수, ...
    """
    chunk = clean_text(chunk)

    if not chunk:
        return None

    hyphen_match = re.match(
        r"^(.{1,80}?)\s*[-–—:]\s*(.+)$",
        chunk,
    )

    if hyphen_match:
        label = clean_text(hyphen_match.group(1))
        ingredients_text = clean_text(hyphen_match.group(2))
    else:
        water_pos = chunk.find("정제수")

        if water_pos > 0:
            label = clean_text(chunk[:water_pos])
            ingredients_text = clean_text(chunk[water_pos:])
        else:
            return {
                "variant_name": "수동확인필요",
                "formula_version": "CURRENT",
                "raw_ingredients": chunk,
                "parse_style": "BULLET",
                "parse_status": "REVIEW",
            }

    variant_name, version = parse_formula_version(label)

    return {
        "variant_name": variant_name or "기본",
        "formula_version": version,
        "raw_ingredients": ingredients_text,
        "parse_style": "BULLET",
        "parse_status": "OK" if ingredients_text else "EMPTY",
    }


def parse_bullet_variants(raw):
    if BULLET not in raw:
        return []

    blocks = []

    for chunk in raw.split(BULLET):
        parsed = parse_bullet_chunk(chunk)

        if parsed:
            blocks.append(parsed)

    has_renewal = any(
        b["formula_version"] == "RENEWAL"
        for b in blocks
    )

    for block in blocks:
        if block["formula_version"] is None:
            block["formula_version"] = (
                "ORIGINAL"
                if has_renewal
                else "CURRENT"
            )

    return blocks


def parse_variants(raw):
    """
    우선순위:
    1) ■옵션명 형식
    2) [옵션명] 형식
    3) 일반 단일 전성분
    """
    raw = clean_text(raw)

    if not raw:
        return []

    if BULLET in raw:
        blocks = parse_bullet_variants(raw)

        if blocks:
            return blocks

    if BRACKET_MARKER.search(raw):
        blocks = parse_bracket_variants(raw)

        if blocks:
            return blocks

    return [{
        "variant_name": "기본",
        "formula_version": "CURRENT",
        "raw_ingredients": raw,
        "parse_style": "SINGLE",
        "parse_status": "OK",
    }]


def output_path(filename):
    if hasattr(config, "OUTPUT"):
        return config.OUTPUT / filename

    if hasattr(config, "OUTPUT_DIR"):
        return config.OUTPUT_DIR / filename

    return config.MANUAL_CSV.parent / filename


def main():
    df = pd.read_csv(
        config.MANUAL_CSV,
        encoding="utf-8-sig",
    )

    products = []
    variants = []
    ingredients = []
    variant_ingredients = []

    ingredient_map = {}

    next_product_id = 1
    next_variant_id = 1
    next_ingredient_id = 1

    products_with_ingredients = 0
    multi_variant_products = 0
    review_variants = 0

    for _, row in df.iterrows():
        product_name = clean_text(
            row.get("PRODUCT_NAME", "")
        )

        if not product_name:
            continue

        raw = clean_text(
            row.get("RAW_INGREDIENTS", "")
        )

        product_id = next_product_id
        next_product_id += 1

        products.append({
            "product_id": product_id,
            "product_name": product_name,
            "brand_name": clean_text(row.get("BRAND_NAME", "")),
            "oliveyoung_goods_no": clean_text(row.get("OLIVEYOUNG_GOODS_NO", "")),
            "product_url": clean_text(row.get("PRODUCT_URL", "")),
            "category_primary": clean_text(row.get("CATEGORY_PRIMARY", "")),
            "category_tags": clean_text(row.get("CATEGORY_TAGS", "")),
            "mfds_match_status": clean_text(row.get("MFDS_MATCH_STATUS", "")),
            "mfds_product_name": clean_text(row.get("MFDS_CANDIDATE_PRODUCT_NAME", "")),
            "mfds_match_score": row.get("MFDS_MATCH_SCORE", ""),
            "raw_ingredients_source": raw,
            "ingredient_source_url": clean_text(row.get("INGREDIENT_SOURCE_URL", "")),
            "ingredient_status": clean_text(row.get("INGREDIENT_STATUS", "")),
            "note": clean_text(row.get("NOTE", "")),
        })

        parsed_variants = parse_variants(raw)

        if not parsed_variants:
            continue

        products_with_ingredients += 1

        if len(parsed_variants) > 1:
            multi_variant_products += 1

        for block in parsed_variants:
            variant_id = next_variant_id
            next_variant_id += 1

            if block["parse_status"] == "REVIEW":
                review_variants += 1

            variants.append({
                "variant_id": variant_id,
                "product_id": product_id,
                "variant_name": block["variant_name"],
                "formula_version": block["formula_version"],
                "raw_ingredients": block["raw_ingredients"],
                "parse_style": block["parse_style"],
                "parse_status": block["parse_status"],
            })

            for order_no, ingredient_name in enumerate(
                split_ingredients(block["raw_ingredients"]),
                start=1,
            ):
                key = normalize_text(ingredient_name)

                if not key:
                    continue

                if key not in ingredient_map:
                    ingredient_map[key] = next_ingredient_id

                    ingredients.append({
                        "ingredient_id": next_ingredient_id,
                        "ingredient_name_raw": ingredient_name,
                        "ingredient_name_normalized": key,
                    })

                    next_ingredient_id += 1

                variant_ingredients.append({
                    "variant_id": variant_id,
                    "ingredient_id": ingredient_map[key],
                    "ingredient_order": order_no,
                })

    products_path = getattr(
        config,
        "DB_PRODUCTS_CSV",
        output_path("05_products_for_db.csv"),
    )

    ingredients_path = getattr(
        config,
        "DB_INGREDIENTS_CSV",
        output_path("05_ingredients_for_db.csv"),
    )

    variants_path = output_path(
        "05_product_variants_for_db.csv"
    )

    variant_ingredients_path = output_path(
        "05_variant_ingredients_for_db.csv"
    )

    pd.DataFrame(products).to_csv(
        products_path,
        index=False,
        encoding="utf-8-sig",
    )

    pd.DataFrame(
        variants,
        columns=[
            "variant_id",
            "product_id",
            "variant_name",
            "formula_version",
            "raw_ingredients",
            "parse_style",
            "parse_status",
        ],
    ).to_csv(
        variants_path,
        index=False,
        encoding="utf-8-sig",
    )

    pd.DataFrame(
        ingredients,
        columns=[
            "ingredient_id",
            "ingredient_name_raw",
            "ingredient_name_normalized",
        ],
    ).to_csv(
        ingredients_path,
        index=False,
        encoding="utf-8-sig",
    )

    pd.DataFrame(
        variant_ingredients,
        columns=[
            "variant_id",
            "ingredient_id",
            "ingredient_order",
        ],
    ).to_csv(
        variant_ingredients_path,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print("=== DB 변환 완료 ===")
    print("전체 제품:", len(products))
    print("전성분 입력된 제품:", products_with_ingredients)
    print("멀티 옵션 제품:", multi_variant_products)
    print("생성된 variant:", len(variants))
    print("고유 성분:", len(ingredients))
    print("variant-성분 관계:", len(variant_ingredients))
    print("수동 확인 필요한 variant:", review_variants)

    print()
    print("products:", products_path)
    print("product_variants:", variants_path)
    print("ingredients:", ingredients_path)
    print("variant_ingredients:", variant_ingredients_path)


if __name__ == "__main__":
    main()
