"""Offline tests: sync swap and guardrails without Supabase, GPU, or Ollama."""
import csv
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from app.retrieval import supabase_sync as sync
from app.retrieval.build_index import build_records
from app.retrieval.embedding.vector_store import VectorStore


def fixture_rows():
    csvfile = Path(__file__).parent / "supabase_test_output" / "supabase_products_raw.csv"
    with csvfile.open("r", encoding="utf-8-sig", newline="") as fp:
        return list(csv.DictReader(fp))


def prepare(monkeypatch, tmp_path):
    source = Path(__file__).resolve().parents[1] / "data"
    data = tmp_path / "data"
    data.mkdir()
    shutil.copy2(source / "products.csv", data / "products.csv")
    shutil.copytree(source / "index", data / "index")
    monkeypatch.setattr(sync, "DATA_DIR", data)
    monkeypatch.setattr(sync, "PRODUCTS_CSV", data / "products.csv")
    monkeypatch.setattr(sync, "INDEX_DIR", data / "index")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "dummy_test_key")
    return data


def fake_build(csv_path, index_path):
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    records = build_records(df)
    vectors = np.ones((len(records), 3), dtype="float32")
    VectorStore.build(records, vectors, "offline_test_embedder").save(index_path)


def test_first_sync_new_snapshot_and_backup(monkeypatch, tmp_path):
    data = prepare(monkeypatch, tmp_path)
    records = fixture_rows()
    assert len(records) == 145
    monkeypatch.setattr(sync, "_fetch_all", lambda *_: records)
    monkeypatch.setattr(sync, "_build_index", fake_build)
    sync.synchronize_products()
    assert len(sync._read_csv(data / "products.csv")) == 145
    assert len(sync._read_csv(data / "backup" / "products.csv")) == 146
    assert VectorStore.load(data / "index").records[0]["product_id"] == int(records[0]["product_id"])
    assert len(VectorStore.load(data / "backup" / "index").records) == 146
    assert sync._index_matches(sync._read_csv(data / "products.csv"))
    # Same remote data must not regenerate an index or rotate the backup.
    def should_not_build(*_):
        raise AssertionError("No change should not rebuild")
    monkeypatch.setattr(sync, "_build_index", should_not_build)
    sync.synchronize_products()
    assert len(sync._read_csv(data / "backup" / "products.csv")) == 146


def test_reject_15_fewer_or_missing_rows(monkeypatch, tmp_path):
    data = prepare(monkeypatch, tmp_path)
    local = sync._read_csv(data / "products.csv")
    remote = fixture_rows()[:130]  # 16 fewer than the original 146.
    monkeypatch.setattr(sync, "_fetch_all", lambda *_: remote)
    monkeypatch.setattr(sync, "_build_index", lambda *_: (_ for _ in ()).throw(AssertionError("should not build")))
    sync.synchronize_products()
    assert sync._read_csv(data / "products.csv") == local
    assert VectorStore.load(data / "index").meta["count"] == 146


def test_reject_malformed_id_and_missing_required(monkeypatch, tmp_path):
    data = prepare(monkeypatch, tmp_path)
    for modified in ("id", "ingredient", "column"):
        rows = [dict(x) for x in fixture_rows()]
        if modified == "id":
            rows[1]["product_id"] = rows[0]["product_id"]
        elif modified == "ingredient":
            rows[0]["ingredients"] = ""
        else:
            rows[0].pop("category")
        monkeypatch.setattr(sync, "_fetch_all", lambda *_: rows)
        sync.synchronize_products()
        assert len(sync._read_csv(data / "products.csv")) == 146


def test_index_failure_keeps_previous_version(monkeypatch, tmp_path):
    data = prepare(monkeypatch, tmp_path)
    monkeypatch.setattr(sync, "_fetch_all", lambda *_: fixture_rows())
    monkeypatch.setattr(sync, "_build_index", lambda *_: (_ for _ in ()).throw(RuntimeError("embedding failed")))
    sync.synchronize_products()
    assert len(sync._read_csv(data / "products.csv")) == 146
    assert VectorStore.load(data / "index").meta["count"] == 146
