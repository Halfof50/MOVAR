"""Supabase products -> local CSV/index: start-up-only guarded synchronization.

The existing Hybrid retrieval, Qwen prompting, and API payloads are untouched.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import tempfile
import time
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import DATA_DIR, INDEX_DIR, PRODUCTS_CSV

# The currently verified 26-column Supabase products table.
EXPECTED_COLUMNS = (
    "product_id", "product_name", "brand_name", "oliveyoung_goods_no", "product_url",
    "category_primary", "category_tags", "raw_ingredients_source", "ingredient_source_url",
    "ingredient_status", "note", "created_at", "source_key", "name", "volume",
    "spec", "ingredients", "link", "price", "rating", "reviews", "image",
    "symptom_tags", "category", "updated_at", "name_clean",
)
REQUIRED_VALUES = ("product_id", "name", "category", "ingredients")
PAGE_SIZE = 500
TIMEOUT_SECONDS = 5  # Per HTTP request, not a total synchronization deadline.
DROP_LIMIT = 15  # >= 15 fewer rows or vanished existing IDs -> reject the refresh.


def log(message: str) -> None:
    print(f"[DB SYNC] {message}", flush=True)


def _load_env_file() -> None:
    # Read only for this feature; never overwrite process environment variables.
    env_file = DATA_DIR.parent / ".env"
    if not env_file.is_file():
        return
    for raw in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] in ("'", '"') and value[-1] == value[0]:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _is_empty(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _fetch_all(url: str, key: str) -> list[dict]:
    endpoint = url.rstrip("/") + "/rest/v1/products"
    headers = {"apikey": key, "Accept": "application/json", "Prefer": "count=exact"}
    if key.startswith("eyJ"):
        headers["Authorization"] = "Bearer " + key
    records = []
    expected_count = None
    offset = 0
    while True:
        params = urlencode({"select": "*", "order": "product_id.asc", "limit": PAGE_SIZE,
                            "offset": offset})
        req = Request(endpoint + "?" + params, headers=headers)
        try:
            with urlopen(req, timeout=TIMEOUT_SECONDS) as response:
                rows = json.loads(response.read())
                content_range = response.headers.get("Content-Range", "")
        except HTTPError as exc:
            raise RuntimeError(f"Supabase HTTP {exc.code}") from exc
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(f"Supabase 연결 실패 또는 시간 초과: {exc}") from exc
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise ValueError("Supabase 응답이 상품 목록 형식이 아닙니다.")
        if expected_count is None:
            count_text = content_range.rsplit("/", 1)[-1] if "/" in content_range else ""
            if not count_text.isdigit():
                raise ValueError("Supabase의 전체 상품 수를 확인할 수 없습니다.")
            expected_count = int(count_text)
        records.extend(rows)
        log(f"상품 조회 중: {len(records)}/{expected_count}건")
        if len(records) >= expected_count:
            break
        if not rows or len(rows) < PAGE_SIZE:
            # Do not promote an incomplete result even if the server returned 200.
            raise ValueError(f"상품 일부만 조회됨: {len(records)}/{expected_count}건")
        offset += len(rows)
        if offset > 1_000_000:
            raise ValueError("페이지 수가 비정상적으로 많아 조회를 중단합니다.")
    if len(records) != expected_count:
        raise ValueError(f"조회된 상품 수 불일치: {len(records)}/{expected_count}건")
    return records


def _validate(rows: list[dict], old_rows: list[dict]) -> None:
    log("필수 컬럼, 유효 상품, 중복 ID 및 데이터 감소 여부 확인 중...")
    if not rows:
        raise ValueError("Supabase에서 상품을 0건 반환했습니다.")
    for i, row in enumerate(rows, 1):
        missing = [col for col in EXPECTED_COLUMNS if col not in row]
        if missing:
            raise ValueError(f"{i}번째 상품에 컬럼 누락: {missing}")
        absent = [col for col in REQUIRED_VALUES if _is_empty(row.get(col))]
        if absent:
            raise ValueError(f"{i}번째 상품의 필수값 누락: {absent}")
        try:
            pid = int(row["product_id"])
            if pid <= 0 or str(row["product_id"]).strip() != str(pid):
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError(f"{i}번째 상품의 product_id가 유효하지 않습니다.") from None
    ids = [int(row["product_id"]) for row in rows]
    if len(ids) != len(set(ids)):
        duplicates = [k for k, count in Counter(ids).items() if count > 1]
        raise ValueError(f"중복 상품 ID 발견: {duplicates[:5]}")
    if old_rows:
        if len(old_rows) - len(rows) >= DROP_LIMIT:
            raise ValueError(f"정상 상품 수 감소가 {DROP_LIMIT}건 이상입니다: {len(old_rows)} -> {len(rows)}")
        if "product_id" in old_rows[0]:
            old_ids = {int(r["product_id"]) for r in old_rows if not _is_empty(r.get("product_id"))}
            missing_count = len(old_ids - set(ids))
            if missing_count >= DROP_LIMIT:
                raise ValueError(f"기존 상품 ID {missing_count}개 누락 (허용 기준 {DROP_LIMIT}개 미만)")
        else:
            # The original 12-column CSV has no product_id; compare names for first migration.
            old_names = {str(r.get("name", "")).strip() for r in old_rows}
            new_names = {str(r.get("name", "")).strip() for r in rows}
            missing_count = len(old_names - new_names)
            if missing_count >= DROP_LIMIT:
                raise ValueError(f"기존 상품명 {missing_count}개 누락 (허용 기준 {DROP_LIMIT}개 미만)")
    log(f"데이터 검증 통과: 정상 상품 {len(rows)}개")


def _read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        return list(csv.DictReader(fp))


def _fingerprint(rows: list[dict]) -> str:
    # Every supplied column participates: price/image and non-embedding changes update CSV too.
    # Normalize JSON numbers, CSV strings, and nulls to a shared representation.
    normalized = [
        {col: "" if _is_empty(row.get(col)) else str(row[col]) for col in EXPECTED_COLUMNS}
        for row in rows
    ]
    normalized.sort(key=lambda row: int(row["product_id"]))
    body = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _index_matches(rows: list[dict]) -> bool:
    records_path = INDEX_DIR / "records.json"
    meta_path = INDEX_DIR / "meta.json"
    vectors_path = INDEX_DIR / "vectors.npy"
    if not (records_path.is_file() and meta_path.is_file() and vectors_path.is_file()):
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        indexed = json.loads(records_path.read_text(encoding="utf-8"))
        if int(meta.get("count", -1)) != len(rows) or len(indexed) != len(rows):
            return False
        # Check exact correspondence with the CSV (including legacy row IDs).
        for i, (source, rec) in enumerate(zip(rows, indexed), 1):
            expected_id = int(source["product_id"]) if not _is_empty(source.get("product_id")) else i
            if int(rec.get("product_id", -1)) != expected_id:
                return False
            for field in ("name", "category", "ingredients", "spec", "image", "link"):
                if str(rec.get(field) or "") != str(source.get(field) or ""):
                    return False
        # Ensure the vector matrix exists and has the same number of entries.
        import numpy as np
        vec = np.load(vectors_path, mmap_mode="r")
        return vec.ndim == 2 and vec.shape[0] == len(rows)
    except (ValueError, KeyError, OSError, TypeError, json.JSONDecodeError):
        return False


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=EXPECTED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _build_index(csv_path: Path, index_path: Path) -> None:
    # The original Document creation and embedding functions are reused unchanged.
    from app.retrieval.build_index import build_records, load_products
    from app.retrieval.embedding.embedding_model import get_embedder
    from app.retrieval.embedding.vector_store import VectorStore

    df = load_products(csv_path)
    records = build_records(df)
    texts = [record["embed_text"] for record in records]
    log(f"상품 {len(texts)}개 Document 생성 완료. 임베딩 모델 로드 중...")
    embedder = get_embedder("auto")  # Never silently replace the actual model with hashing.
    vectors = embedder.encode(texts)
    VectorStore.build(records, vectors, embedder.name).save(index_path)
    if len(records) != len(df):
        raise RuntimeError("인덱스 생성 상품 개수가 맞지 않습니다.")
    log(f"상품 {len(records)}개 임베딩 및 새 벡터 인덱스 생성 완료")


def _promote(staged_csv: Path, staged_index: Path, work_dir: Path) -> None:
    """Swap the paired CSV+index with rollback if this Python process sees an error."""
    backup_dir = DATA_DIR / "backup"
    earlier_backup = work_dir / "earlier_backup"
    have_old_csv = PRODUCTS_CSV.is_file()
    have_old_index = INDEX_DIR.is_dir()
    if have_old_csv != have_old_index:
        raise RuntimeError("현재 CSV와 인덱스 중 하나만 있습니다. 안전한 교체를 중단합니다.")
    new_backup = work_dir / "new_backup"
    old_moved = False
    new_csv_moved = False
    new_index_moved = False
    saved_old_backup = False
    try:
        if backup_dir.exists():
            os.replace(backup_dir, earlier_backup)
            saved_old_backup = True
        if have_old_csv:
            new_backup.mkdir()
            os.replace(PRODUCTS_CSV, new_backup / "products.csv")
            os.replace(INDEX_DIR, new_backup / "index")
            old_moved = True
        os.replace(staged_csv, PRODUCTS_CSV)
        new_csv_moved = True
        os.replace(staged_index, INDEX_DIR)
        new_index_moved = True
        if not _index_matches(_read_csv(PRODUCTS_CSV)):
            raise RuntimeError("새 CSV와 벡터 인덱스의 상품 목록 검증 실패")
        if old_moved:
            os.replace(new_backup, backup_dir)
            log("직전 정상 CSV + 인덱스를 data/backup/에 보관 (백업 최대 1개)")
        elif saved_old_backup:
            os.replace(earlier_backup, backup_dir)
            saved_old_backup = False
        # Only after success will TemporaryDirectory delete the displaced older backup.
        log("최신 CSV + 벡터 인덱스 교체 완료")
    except Exception:
        # Roll back to the previous working pair; never leave mismatched files on a normal error.
        if new_index_moved and INDEX_DIR.exists():
            shutil.rmtree(INDEX_DIR)
        if new_csv_moved and PRODUCTS_CSV.exists():
            PRODUCTS_CSV.unlink()
        if new_backup.exists():
            if (new_backup / "products.csv").exists():
                os.replace(new_backup / "products.csv", PRODUCTS_CSV)
            if (new_backup / "index").exists():
                os.replace(new_backup / "index", INDEX_DIR)
        if saved_old_backup and earlier_backup.exists():
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            os.replace(earlier_backup, backup_dir)
        raise


def synchronize_products() -> None:
    """Best-effort startup sync; failures retain the previous local CSV and index."""
    start = time.perf_counter()
    log("시작 시 Supabase 상품 DB 검증 과정 진행 중...")
    _load_env_file()
    url = os.getenv("SUPABASE_URL", "").strip()
    key = (os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY") or "").strip()
    if not url or not key:
        log("Supabase 설정 없음 — 기존 로컬 CSV/벡터 인덱스 사용")
        return
    if not url.startswith("https://"):
        log("Supabase URL 형식 오류 — 기존 로컬 CSV/벡터 인덱스 사용")
        return
    try:
        local = _read_csv(PRODUCTS_CSV)
        incoming = _fetch_all(url, key)
        _validate(incoming, local)
        if (local and "product_id" in local[0]
                and _fingerprint(incoming) == _fingerprint(local)
                and _index_matches(local)):
            log(f"DB 변경 없음 — 기존 벡터 인덱스 사용 ({time.perf_counter()-start:.2f}초)")
            return
        log("DB 변경 또는 기존 인덱스 불일치 감지 — 새 인덱스 준비")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".db_sync_", dir=DATA_DIR) as temp:
            staged = Path(temp)
            new_csv = staged / "products.csv"
            new_index = staged / "index"
            _write_csv(new_csv, incoming)
            _build_index(new_csv, new_index)
            _promote(new_csv, new_index, staged)
        log(f"DB 동기화 성공 — 현재 상품 {len(incoming)}개 ({time.perf_counter()-start:.2f}초)")
    except Exception as exc:
        log(f"DB 동기화 실패: {type(exc).__name__}: {exc}")
        if PRODUCTS_CSV.is_file() and _index_matches(_read_csv(PRODUCTS_CSV)):
            log("기존 로컬 CSV + 벡터 인덱스로 계속 실행")
        else:
            log("주의: 기존 로컬 CSV/인덱스도 검증되지 않았습니다. 추천 API 실행 전 확인 필요")
