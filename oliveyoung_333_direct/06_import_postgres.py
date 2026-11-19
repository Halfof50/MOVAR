"""새 엑셀 기반 4개 상품 CSV 적재. 옵션/성분 테이블과 recommendations.variant_id 유지.
먼저 이번 버전 00_migrate_products.sql 실행. 05 파일을 같은 폴더에 둘 것.
ID는 source_key/옵션명+버전/정규화 성분명으로 매핑. TRUNCATE CASCADE 없음.
"""
import argparse
import csv
import getpass
import hashlib
import importlib.util
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

BASE = Path(__file__).resolve().parent


def converter_module():
    spec = importlib.util.spec_from_file_location('product_converter', BASE/'05_build_db_tables_smart.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unique_ids(rows, name):
    ids = [int(r[name]) for r in rows]
    if len(ids) != len(set(ids)) or any(i <= 0 for i in ids):
        raise ValueError(f'{name} 임시 ID 중복 또는 잘못된 ID')
    return set(ids)


def load_bundle(directory, m):
    manifest = json.loads((directory/'05_manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format') != 'products-with-variants-v1':
        raise ValueError('이번 05번으로 CSV를 다시 생성하세요.')
    tables = []
    for name, columns in m.FILES.items():
        path = directory/name
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['files'].get(name):
            raise ValueError(f'{name}: 생성 이후 파일이 변경되었거나 다른 실행 결과가 섞였습니다. 05번을 다시 실행하세요.')
        with path.open(encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            if reader.fieldnames != columns:
                raise ValueError(f'{name}: 컬럼이 맞지 않습니다.')
            tables.append(list(reader))
    p, v, i, links, review = tables
    validated, duplicates = m.validate(p)
    if duplicates or len(validated) != len(p):
        raise ValueError('상품 중복이 있습니다.')
    pids, vids, iids = unique_ids(p, 'product_id'), unique_ids(v, 'variant_id'), unique_ids(i, 'ingredient_id')
    if not v:
        raise ValueError('옵션이 0개입니다.')
    keys = [r['source_key'] for r in p]
    if len(keys) != len(set(keys)) or any(r['source_key'] != m.source_key(r['link']) for r in p):
        raise ValueError('상품 source_key가 맞지 않습니다.')
    if any(int(r['product_id']) not in pids for r in v):
        raise ValueError('옵션의 상품 연결이 잘못되었습니다.')
    variant_keys = [(r['product_id'], r['variant_name'], r['formula_version']) for r in v]
    if len(variant_keys) != len(set(variant_keys)):
        raise ValueError('동일 옵션명/버전 중복')
    norms = [r['ingredient_name_normalized'] for r in i]
    if len(norms) != len(set(norms)) or any(not k for k in norms):
        raise ValueError('성분 정규화 키가 잘못되었습니다.')
    orders, counts = set(), Counter()
    for r in links:
        vi, ii, order = int(r['variant_id']), int(r['ingredient_id']), int(r['ingredient_order'])
        if vi not in vids or ii not in iids or order <= 0 or (vi, order) in orders:
            raise ValueError('옵션-성분 연결 오류')
        orders.add((vi, order)); counts[vi] += 1
    for r in v:
        vi = int(r['variant_id'])
        if int(r['ingredient_count']) != counts[vi] or any((vi,n) not in orders for n in range(1,counts[vi]+1)):
            raise ValueError('성분 개수/순서 불일치')
    return tables


def import_bundle(conn, tables, m):
    from psycopg2.extras import execute_values
    products, variants, ingredients, relations, review = tables
    with conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout='10s'")
            cur.execute("SET LOCAL statement_timeout='120s'")
            cur.execute('''LOCK TABLE public.products, public.product_variants, public.ingredients,
                public.variant_ingredients, public.recommendations IN SHARE ROW EXCLUSIVE MODE''')
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='products'")
            if not set(m.COLUMNS+['source_key', 'updated_at', 'product_name', 'product_url']).issubset({r[0] for r in cur.fetchall()}):
                raise ValueError('이번 버전의 00_migrate_products.sql을 먼저 실행하세요.')
            # 기존 수동 ID 적재 후에도 시퀀스가 최대 ID보다 크도록 보정.
            for table, pk in [('products','product_id'), ('product_variants','variant_id'), ('ingredients','ingredient_id')]:
                cur.execute('SELECT pg_get_serial_sequence(%s,%s)', ('public.'+table,pk))
                sequence = cur.fetchone()[0]
                if sequence is None:
                    raise ValueError(f'{table}.{pk}에 자동 ID 시퀀스가 없습니다.')
                cur.execute(f'SELECT COALESCE(MAX({pk}),0) FROM public.{table}')
                maximum = cur.fetchone()[0]
                cur.execute('SELECT setval(%s::regclass, GREATEST(nextval(%s::regclass), %s), true)', (sequence,sequence,maximum))
            product_map, variant_map, ingredient_map = {}, {}, {}
            product_columns = ['source_key'] + m.COLUMNS + ['product_name','product_url','raw_ingredients_source','oliveyoung_goods_no']
            for p in products:
                values = [p['source_key']]
                for col in m.COLUMNS:
                    value = p[col] or None
                    if value is not None and col in ('price','rating'):
                        value = Decimal(value)
                    elif value is not None and col == 'reviews':
                        value = int(Decimal(value))
                    values.append(value)
                goods = p['source_key'].split(':',1)[1] if p['source_key'].startswith('oliveyoung:') else None
                values.extend([p['name'],p['link'],p['ingredients'],goods])
                updates = ','.join(f'{c}=EXCLUDED.{c}' for c in product_columns if c != 'source_key')
                cur.execute('INSERT INTO public.products ('+','.join(product_columns)+') VALUES ('+','.join(['%s']*len(values))+') '
                            +'ON CONFLICT (source_key) DO UPDATE SET '+updates+', updated_at=now() RETURNING product_id', values)
                product_map[int(p['product_id'])] = cur.fetchone()[0]
            for v in variants:
                product_id = product_map[int(v['product_id'])]
                natural_key = (product_id,v['variant_name'],v['formula_version'])
                cur.execute('''SELECT variant_id, raw_ingredients FROM public.product_variants
                    WHERE product_id=%s AND variant_name=%s AND formula_version=%s''', natural_key)
                existing = cur.fetchone()
                if existing and existing[1] != v['raw_ingredients']:
                    cur.execute('SELECT 1 FROM public.recommendations WHERE variant_id=%s LIMIT 1',(existing[0],))
                    if cur.fetchone():
                        raise ValueError(f'추천 기록이 참조하는 옵션({existing[0]})의 전성분이 달라졌습니다. 전체 변경을 취소합니다.')
                cols = m.VARIANT_COLS[1:]
                values = [product_id] + [int(v[c]) if c=='ingredient_count' else v[c] for c in cols[1:]]
                updates = ','.join(f'{c}=EXCLUDED.{c}' for c in cols if c not in ('product_id','variant_name','formula_version'))
                cur.execute('INSERT INTO public.product_variants ('+','.join(cols)+') VALUES ('+','.join(['%s']*len(values))+') '
                            +'ON CONFLICT (product_id,variant_name,formula_version) DO UPDATE SET '+updates+' RETURNING variant_id',values)
                variant_map[int(v['variant_id'])] = cur.fetchone()[0]
            active_products, active_variants = list(product_map.values()), list(variant_map.values())
            cur.execute('SELECT variant_id FROM public.recommendations WHERE NOT (variant_id=ANY(%s)) LIMIT 1',(active_variants,))
            if cur.fetchone():
                raise ValueError('새 목록에서 제외될 옵션을 참조하는 추천 기록이 있습니다. 삭제 없이 전체 변경을 취소합니다.')
            # 추천 이력의 성분 연결도 모르는 사이 변경하지 않는다.
            new_names = {int(i['ingredient_id']):i['ingredient_name_normalized'] for i in ingredients}
            new_formulas = {}
            for r in relations:
                new_formulas.setdefault(variant_map[int(r['variant_id'])], []).append((int(r['ingredient_order']),new_names[int(r['ingredient_id'])]))
            cur.execute('SELECT DISTINCT variant_id FROM public.recommendations')
            for (vi,) in cur.fetchall():
                cur.execute('''SELECT vi.ingredient_order,i.ingredient_name_normalized FROM public.variant_ingredients vi
                    JOIN public.ingredients i USING(ingredient_id) WHERE vi.variant_id=%s ORDER BY vi.ingredient_order''',(vi,))
                if cur.fetchall() != sorted(new_formulas.get(vi,[])):
                    raise ValueError(f'추천에 사용된 옵션({vi})의 성분 연결이 달라집니다. 전체 변경을 취소합니다.')
            for i in ingredients:
                cur.execute('''INSERT INTO public.ingredients (ingredient_name_raw,ingredient_name_normalized)
                    VALUES (%s,%s) ON CONFLICT (ingredient_name_normalized) DO UPDATE
                    SET ingredient_name_normalized=EXCLUDED.ingredient_name_normalized RETURNING ingredient_id''',
                    (i['ingredient_name_raw'],i['ingredient_name_normalized']))
                ingredient_map[int(i['ingredient_id'])] = cur.fetchone()[0]
            # 목표는 새 엑셀 목록으로 교체. 연결 삭제도 트랜잭션 안에서만 수행.
            cur.execute('DELETE FROM public.variant_ingredients')
            cur.execute('DELETE FROM public.product_variants WHERE NOT (variant_id=ANY(%s))',(active_variants,))
            cur.execute('DELETE FROM public.products WHERE NOT (product_id=ANY(%s))',(active_products,))
            mapped_links = [(variant_map[int(r['variant_id'])],ingredient_map[int(r['ingredient_id'])],int(r['ingredient_order'])) for r in relations]
            if mapped_links:
                execute_values(cur,'INSERT INTO public.variant_ingredients (variant_id,ingredient_id,ingredient_order) VALUES %s',mapped_links)
            cur.execute('DELETE FROM public.ingredients i WHERE NOT EXISTS (SELECT 1 FROM public.variant_ingredients vi WHERE vi.ingredient_id=i.ingredient_id)')
            actual=[]
            for table in ('products','product_variants','ingredients','variant_ingredients'):
                cur.execute(f'SELECT COUNT(*) FROM public.{table}')
                actual.append(cur.fetchone()[0])
            expected=[len(products),len(variants),len(ingredients),len(relations)]
            if actual != expected:
                raise ValueError(f'적재 건수 불일치: {actual} / 기대값 {expected}')
    return actual


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir',type=Path,default=BASE/'data/output')
    parser.add_argument('--validate-only',action='store_true',help='DB 접속 없이 CSV 검증만 실행')
    args=parser.parse_args()
    m=converter_module()
    tables=load_bundle(args.input_dir,m)
    print('CSV 검증 완료:',[len(t) for t in tables], '(상품/옵션/성분/연결/검토)')
    if args.validate_only:
        return
    print('새 엑셀 목록으로 상품/옵션/성분을 교체합니다. 추천에 사용된 항목의 삭제/성분 변경은 거부합니다.')
    host=input('HOST (Supabase Connect의 DB host, localhost는 로컬): ').strip()
    if not host:
        raise ValueError('HOST를 입력하세요.')
    port=input('PORT [5432]: ').strip() or '5432'
    dbname=input('DB NAME [postgres]: ').strip() or 'postgres'
    user=input('USER [postgres]: ').strip() or 'postgres'
    password=getpass.getpass('DB PASSWORD: ')
    import psycopg2
    conn=psycopg2.connect(host=host,port=port,dbname=dbname,user=user,password=password,
                          sslmode='prefer' if host in ('localhost','127.0.0.1','::1') else 'require',connect_timeout=15)
    try:
        counts=import_bundle(conn,tables,m)
        print('IMPORT 완료 (상품/옵션/성분/연결):',counts)
    finally:
        conn.close()


if __name__=='__main__':
    main()
