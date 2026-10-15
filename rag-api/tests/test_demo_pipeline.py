"""Offline smoke checks; no GPU or Ollama connection required."""
import numpy as np
from fastapi.testclient import TestClient
from app.retrieval.embedding.vector_store import VectorStore
from app.retrieval.retriever import Retriever
from app.services.recommendation_service import RecommendationService
from app.main import app
import app.main as api


class FakeEmbedder:
    requires_fit = False
    def __init__(self, store):
        self.name = store.meta["model"]
        self.vector = store.vectors[0]
    def encode(self, texts):
        return np.stack([self.vector for _ in texts])


class FakeQwen:
    def available(self):
        return True, "mock success"
    def score(self, prompt, candidate_count):
        assert f"[C{candidate_count:02d}]" in prompt and "- 전성분:" in prompt
        return {f"C{i:02d}": 101.0-i for i in range(1, candidate_count+1)}


def service():
    store = VectorStore.load()
    return RecommendationService(
        retriever=Retriever(store=store, embedder=FakeEmbedder(store)),
        llm=FakeQwen(),
    )


def test_hybrid_seven_plus_fifteen():
    result = service().recommend({"hair_loss": 3, "dandruff": 2})
    assert result["status"] == "ok"
    assert result["candidate_count"] == 22
    assert result["retrieval"] == {"embedding_count": 7, "ingredient_count": 15}
    assert len(set(result["candidate_ids"])) == 22
    assert [r["llm_score"] for r in result["recommendations"]] == [100, 99, 98]
    assert result["llm_calls"] == 1


def test_all_zero_does_not_call_llm():
    result = service().recommend({})
    assert result["all_zero"] is True
    assert result["llm_calls"] == 0
    assert len(result["recommendations"]) == 3


def test_invalid_budget_no_fabricated_results():
    result = service().recommend({"hair_loss": 3}, {"max_price": 1})
    assert result["status"] == "empty"
    assert result["recommendations"] == []


def test_api_response(monkeypatch):
    monkeypatch.setattr(api, "get_service", service)
    client = TestClient(app)
    invalid = client.post("/recommend", json={"symptoms":{"hair_loss":4}})
    assert invalid.status_code == 422
    valid = client.post("/recommend", json={"symptoms":{"hair_loss":3},"user_info":{}})
    assert valid.status_code == 200
    assert len(valid.json()["recommendations"]) == 3


def test_selected_category_is_strict_filter():
    # A single category must never be silently padded with other product types.
    for cat in ("shampoo", "scaler", "treatment", "tonic"):
        result = service().recommend({"hair_loss": 3}, plan=[cat])
        assert result["candidate_count"] <= 22
        assert result["candidate_count"] > 0
        assert {r["category"] for r in result["recommendations"]} == {cat}
        assert len(result["candidate_ids"]) == len(set(result["candidate_ids"]))


def test_multiple_categories_are_respected():
    selected = {"shampoo", "tonic"}
    result = service().recommend({"hair_loss": 3}, plan=sorted(selected))
    assert result["status"] == "ok"
    assert result["recommendations"]
    assert {r["category"] for r in result["recommendations"]}.issubset(selected)


def test_api_accepts_selected_categories_and_custom_profile(monkeypatch):
    monkeypatch.setattr(api, "get_service", service)
    client = TestClient(app)
    response = client.post("/recommend", json={
        "symptoms": {"hair_loss": 3},
        "user_info": {"age_group": "25세", "wash_frequency": "주 2회"},
        "categories": ["shampoo"],
    })
    assert response.status_code == 200
    assert {x["category"] for x in response.json()["recommendations"]} == {"shampoo"}


def test_api_rejects_empty_or_unknown_categories(monkeypatch):
    monkeypatch.setattr(api, "get_service", service)
    client = TestClient(app)
    for categories in ([], ["not-a-category"]):
        response = client.post("/recommend", json={"symptoms": {"hair_loss": 3}, "categories": categories})
        assert response.status_code == 422


def test_frontend_contains_new_controls_and_score_wording():
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")
    for cat in ("shampoo", "scaler", "treatment", "tonic"):
        assert f'value="{cat}"' in html
    assert 'id="age-custom"' in html
    assert 'id="wash-custom"' in html
    assert 'const categories=selectedCategories()' in html
    assert 'JSON.stringify({symptoms,user_info,categories})' in html
    assert '(확률 아님)' not in html
