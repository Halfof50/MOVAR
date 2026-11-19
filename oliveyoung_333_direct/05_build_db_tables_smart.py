"""products.xlsx -> 상품/옵션/성분/연결 CSV + 검토 CSV + manifest.
Usage: python 05_build_db_tables_smart.py [--input products.xlsx]
Dependencies: pandas, openpyxl. No config.py/common.py required.
"""
import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

COLUMNS = ['name', 'volume', 'spec', 'ingredients', 'link', 'price', 'rating',
           'reviews', 'image', 'symptom_tags', 'category']
BASE = Path(__file__).resolve().parent


def source_key(link):
    """상품번호/상품 경로 기준. 원본 link 값은 변경하지 않는다."""
    p = urlsplit(link)
    if p.scheme not in ('http', 'https') or not p.hostname:
        raise ValueError('상품 link가 올바른 HTTP(S) URL이 아닙니다.')
    host = p.hostname.lower().removeprefix('www.')
    if host == 'oliveyoung.co.kr':
        goods = parse_qs(p.query).get('goodsNo', [''])[0]
        if not goods:
            raise ValueError('올리브영 link에 goodsNo가 없습니다.')
        return 'oliveyoung:' + goods
    if host == 'hwahae.co.kr':
        parts = p.path.rstrip('/').split('/')
        if len(parts) >= 3 and parts[-1].isdigit() and 'goods' in parts:
            return 'hwahae:' + parts[-1]
    # 알 수 없는 판매처의 쿼리에는 상품 식별자가 있을 수 있으므로 보존한다.
    return host + p.path.rstrip('/') + ('?' + p.query if p.query else '')


def validate(rows):
    result, seen = [], {}
    duplicates = 0
    for line, original in enumerate(rows, 2):
        row = {c: str(original.get(c, '')).strip() for c in COLUMNS}
        if not any(row.values()):
            continue
        for col in ('name', 'ingredients', 'link', 'category'):
            if not row[col]:
                raise ValueError(f'{line}행: {col} 값이 비어 있습니다.')
        for col in ('price', 'rating', 'reviews'):
            value = row[col]
            if not value:
                continue  # 미수집은 0으로 바꾸지 않고 NULL로 저장
            try:
                number = Decimal(value.replace(',', ''))
            except InvalidOperation:
                raise ValueError(f'{line}행: {col} 숫자 오류 ({value})') from None
            if not number.is_finite() or number < 0:
                raise ValueError(f'{line}행: {col}은 0 이상의 유한한 숫자여야 합니다.')
            if col == 'rating' and number > 5:
                raise ValueError(f'{line}행: rating은 0~5여야 합니다.')
            if col == 'reviews':
                if number != number.to_integral_value() or number > 9223372036854775807:
                    raise ValueError(f'{line}행: reviews는 bigint 범위의 정수여야 합니다.')
                row[col] = str(int(number))
            else:
                row[col] = format(number, 'f')
        key = source_key(row['link'])
        if key in seen:
            previous = seen[key]
            # 추적 파라미터만 다른 동일 데이터는 첫 행을 유지한다.
            if any(previous[c] != row[c] for c in COLUMNS if c != 'link'):
                raise ValueError(f'{line}행: 같은 상품({key})의 내용이 다릅니다. 원본에서 확인해 주세요.')
            duplicates += 1
            continue
        seen[key] = row
        result.append(row)
    if not result:
        raise ValueError('유효 상품이 0개입니다. 빈 파일은 적재할 수 없습니다.')
    return result, duplicates


# CSV 안의 ID는 파일 간 연결용이다. 06번에서 DB의 실제 ID로 매핑한다.
PRODUCT_COLS = ['product_id', 'source_key'] + COLUMNS
VARIANT_COLS = ['variant_id', 'product_id', 'variant_name', 'formula_version',
                'raw_ingredients', 'variant_parse_style', 'variant_parse_status',
                'ingredient_parse_style', 'ingredient_parse_status', 'ingredient_count']
INGREDIENT_COLS = ['ingredient_id', 'ingredient_name_raw', 'ingredient_name_normalized']
RELATION_COLS = ['variant_id', 'ingredient_id', 'ingredient_order']
REVIEW_COLS = ['product_id', 'source_key', 'product_name', 'variant_id', 'variant_name',
               'reason', 'raw_ingredients', 'parsed_preview']
FILES = {
    '05_products_for_db.csv': PRODUCT_COLS,
    '05_product_variants_for_db.csv': VARIANT_COLS,
    '05_ingredients_for_db.csv': INGREDIENT_COLS,
    '05_variant_ingredients_for_db.csv': RELATION_COLS,
    '05_parse_review.csv': REVIEW_COLS,
}


def normalize_ingredient(name):
    # 괄호/숫자/하이픈은 보존. 띄어쓰기 차이는 통합한다.
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', name)).casefold()


def split_delimited(text):
    """숫자 명명법(1,2-)과 괄호 속 쉼표를 보존한다."""
    parts, buf, stack = [], [], []
    pairs = {')': '(', ']': '[', '}': '{'}
    balanced = True
    separators = 0
    for i, ch in enumerate(text):
        if ch in '([{':
            stack.append(ch)
        elif ch in pairs:
            if not stack or stack[-1] != pairs[ch]:
                balanced = False
            elif stack:
                stack.pop()
        numeric = ch in ',，' and i > 0 and i+1 < len(text) and text[i-1].isdigit() and text[i+1].isdigit()
        if not stack and ch in ',，;@' and not numeric:
            parts.append(''.join(buf).strip())
            buf = []
            separators += 1
        else:
            buf.append(ch)
    parts.append(''.join(buf).strip())
    return [p for p in parts if p], separators, balanced and not stack


def split_variants(raw):
    # ILN 처방코드는 옵션명이 아니다. 상품의 원문 필드에는 남긴다.
    text = re.sub(r'\s*\[ILN\d+\]\s*$', '', raw).strip()
    text = re.sub(r'\*\s*리뉴얼\s*(전|후)\s*', lambda m: '[리뉴얼 ' + m[1] + '] ', text)
    if '■' in text:
        # 명시적으로 "■옵션명: ..." 형태일 때만 제목으로 바꾼다.
        text = re.sub(r'■\s*([^■\n:]{1,80}):', r'[\1]', text)
    markers = list(re.finditer(r'\[([^\[\]]+)\]', text))
    blocks = []
    if markers:
        prefix = text[:markers[0].start()].strip()
        if prefix:
            # 기존 코드의 첫 대괄호 앞 본품 성분 누락을 방지한다.
            blocks.append(('기본', prefix, 'BRACKET_PREFIX', 'REVIEW_COMPONENT'))
        for i, match in enumerate(markers):
            end = markers[i+1].start() if i+1 < len(markers) else len(text)
            body = text[match.end():end].strip().lstrip(':').strip()
            label = match[1].strip()
            status = 'OK'
            if not body or re.search(r'함유|ppm|\d+\s*pm', label, re.I):
                status = 'REVIEW_LABEL'
            elif re.search(r'증정|토닉|세럼|스케일러|트리트먼트|컨디셔너', label):
                # 구성품도 분리 조회 가능. 추천 가능 옵션인지 별도 검토.
                status = 'REVIEW_COMPONENT'
            blocks.append((label, body, 'BRACKET', status))
    else:
        status = 'REVIEW_BOUNDARY' if re.search(r'■|증정품|본품 전성분|리필 전성분|리뉴얼', text) else 'OK'
        blocks.append(('기본', text, 'SINGLE', status))
    result, names = [], Counter()
    for label, body, style, status in blocks:
        version = 'CURRENT'
        if label == '리뉴얼 전':
            label, version = '기본', 'ORIGINAL'
        elif label == '리뉴얼 후':
            label, version = '기본', 'RENEWAL'
        elif label.startswith('리뉴얼'):
            label, version = label[3:].strip() or '기본', 'RENEWAL'
        names[(label, version)] += 1
        if names[(label, version)] > 1:
            label += f' ({names[(label, version)]})'
            status = 'REVIEW_DUPLICATE_LABEL'
        result.append(dict(variant_name=label, formula_version=version,
                           raw_ingredients=body, variant_parse_style=style,
                           variant_parse_status=status))
    return result


def parse_ingredients(raw):
    parts, separators, balanced = split_delimited(raw)
    if not raw:
        return [], 'EMPTY', 'EMPTY'
    if not balanced:
        return [], 'UNKNOWN', 'REVIEW_BRACKETS'
    if re.search(r'증정품|본품 전성분|리필 전성분|■|\[|\]|리뉴얼', raw):
        return [], 'UNKNOWN', 'REVIEW_BOUNDARY'
    if not separators:
        # 공백만으로 구분된 성분은 다단어 명칭 오분리를 막기 위해 확정 연결하지 않는다.
        return [], 'SPACE' if len(raw.split()) > 1 else 'SINGLE_TOKEN', 'REVIEW_SPACE' if len(raw.split()) > 1 else 'REVIEW'
    # 두 목록의 경계가 쉼표 없이 합쳐진 경우 및 긴 설명문을 검토로 보낸다.
    if any(len(p) > 180 or len(p.split()) >= 5 or re.search(r'전성분|참고|참조|상세페이지', p) for p in parts):
        return [], 'DELIMITED', 'REVIEW_TEXT'
    return parts, 'DELIMITED', 'OK'


def build_tables(rows):
    products, variants, ingredients, relations, review = [], [], [], [], []
    ingredient_map = {}
    for product_id, row in enumerate(rows, 1):
        key = source_key(row['link'])
        products.append(dict(product_id=product_id, source_key=key, **row))
        blocks = split_variants(row['ingredients'])
        # 옵션 종류 숫자까지 원문으로 검증할 수 없는 경우 검토 표시
        option_hint = bool(re.search(r'\d+\s*종|택\s*1', row['name'])) and len(blocks) == 1
        for block in blocks:
            if option_hint and block['variant_parse_status'] == 'OK':
                block['variant_parse_status'] = 'REVIEW_OPTIONS'
            parsed, style, status = parse_ingredients(block['raw_ingredients'])
            if block['variant_parse_status'] in ('REVIEW_LABEL', 'REVIEW_BOUNDARY'):
                parsed, status = [], 'REVIEW_BOUNDARY'
            variant_id = len(variants)+1
            variants.append(dict(variant_id=variant_id, product_id=product_id, **block,
                                 ingredient_parse_style=style, ingredient_parse_status=status,
                                 ingredient_count=len(parsed)))
            if status != 'OK' or block['variant_parse_status'] != 'OK':
                review.append(dict(product_id=product_id, source_key=key, product_name=row['name'],
                                   variant_id=variant_id, variant_name=block['variant_name'],
                                   reason=block['variant_parse_status'] + '/' + status,
                                   raw_ingredients=block['raw_ingredients'], parsed_preview=' | '.join(parsed[:20])))
            for order, name in enumerate(parsed, 1):
                normalized = normalize_ingredient(name)
                if normalized not in ingredient_map:
                    ingredient_id = len(ingredients)+1
                    ingredient_map[normalized] = ingredient_id
                    ingredients.append(dict(ingredient_id=ingredient_id, ingredient_name_raw=name,
                                            ingredient_name_normalized=normalized))
                relations.append(dict(variant_id=variant_id, ingredient_id=ingredient_map[normalized], ingredient_order=order))
    return dict(zip(FILES, (products, variants, ingredients, relations, review)))


def main():
    parser = argparse.ArgumentParser(description='products.xlsx를 상품/옵션/성분/연결 CSV로 변환')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output-dir', type=Path, default=BASE / 'data/output')
    args = parser.parse_args()
    path = args.input or next((p for p in (BASE/'products.xlsx', BASE/'data/input/products.xlsx') if p.exists()), None)
    if path is None or not path.is_file():
        raise FileNotFoundError('products.xlsx를 코드와 같은 폴더에 두거나 --input으로 지정하세요.')
    import pandas as pd
    frame = pd.read_excel(path, sheet_name=0, dtype=str, keep_default_na=False, engine='openpyxl')
    frame.columns = [str(c).strip() for c in frame.columns]
    if list(frame.columns) != COLUMNS:
        raise ValueError(f'첫 시트의 컬럼/순서를 확인하세요: {COLUMNS}')
    rows, duplicates = validate(frame.to_dict('records'))
    tables = build_tables(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = dict(format='products-with-variants-v1', files={})
    for name, columns in FILES.items():
        target = args.output_dir/name
        temporary = target.with_suffix('.tmp')
        with temporary.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(tables[name])
        temporary.replace(target)
        manifest['files'][name] = hashlib.sha256(target.read_bytes()).hexdigest()
        print(f'{name}: {len(tables[name])}행')
    (args.output_dir/'05_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'동일 상품 중복 제거: {duplicates}개')
    print('REVIEW/EMPTY 옵션은 원문을 확인하세요. 불명확한 성분은 자동 연결하지 않습니다.')
    print('CSV ID는 임시 연결키입니다. 실제 DB ID는 06번에서 결정됩니다.')


if __name__ == '__main__':
    main()
