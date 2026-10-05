"""
후보 검색

증상 레벨 → Query 문장 → 벡터 → 유사도 상위 후보.

후보에 붙여서 내보내는 것 (모두 이 단계에서 계산한다)
    증상별 성분 점수와 근거 성분
    유효 성분 목록
    순한 정도 — 증상이 모두 0단계일 때 고르는 기준

검색 단계에서 하드 필터로 쓰는 것
    카테고리, 가격 상한

알레르기와 기피 성분은 이 단계에서 다루지 않는다.
알레르기는 별도 모듈(Allergy RAG)로 분리할 예정이고, 그전까지는 추천 경로에서 뺀다.
"""

from recommendation.config import (
    CANDIDATES_PER_CATEGORY, CATEGORY_QUOTA, TOP_K,
    HYBRID_EMBEDDING_K, HYBRID_INGREDIENT_K,
)
from recommendation.embedding.embedding_model import get_embedder
from recommendation.embedding.vector_store import VectorStore
from recommendation.preprocessing.gentleness import gentleness
from recommendation.preprocessing.ingredient_scores import (
    active_ingredients, ingredient_scores,
)
from recommendation.retrieval.query_builder import (
    build_query, normalize_levels, ranked_symptoms,
)


class Retriever:

    def __init__(self, store=None, embedder=None, backend="auto"):
        self.store = store or VectorStore.load()
        if embedder is not None:
            self.embedder = embedder
        else:
            self.embedder = get_embedder(backend)
            if getattr(self.embedder, "requires_fit", False):
                self.embedder.fit([r["embed_text"] for r in self.store.records])

        model_in_index = self.store.meta.get("model")
        if model_in_index and model_in_index != self.embedder.name:
            raise RuntimeError(
                f"인덱스는 '{model_in_index}' 로 만들어졌고 지금 모델은 '{self.embedder.name}' 입니다.\n"
                "같은 모델로 다시 인덱스를 만들어야 유사도가 맞습니다."
            )

    # ── 검색 ────────────────────────────────────────────

    def retrieve(self, symptoms: dict, profile: dict = None,
                 top_k: int = TOP_K, per_category: bool = True):
        """
        symptoms : {'dandruff': 1, 'hair_loss': 2, ...}
        profile  : {'age_group': '30대', 'wash_frequency': '하루 1회',
                    'max_price': 40000, ...}
        """
        profile = profile or {}
        levels = normalize_levels(symptoms)

        filters = {}
        if profile.get("max_price"):
            filters["max_price"] = int(profile["max_price"])
        if profile.get("exclude_product_ids"):
            filters["exclude_ids"] = list(profile["exclude_product_ids"])

        if per_category:
            quota = profile.get("category_quota") or CATEGORY_QUOTA
            qtexts = {c: build_query(levels) for c in quota}
            qvecs = {c: self.embedder.encode([t])[0] for c, t in qtexts.items()}
            candidates = self.store.search_by_category(qvecs, quota, **filters)
            query_text = build_query(levels)
        else:
            query_text = build_query(levels)
            qvec = self.embedder.encode([query_text])[0]
            candidates = self.store.search(qvec, top_k=top_k, **filters)

        candidates = [self._annotate(c, profile) for c in candidates]

        return {
            "query": query_text,
            "levels": levels,
            "priority": ranked_symptoms(levels),
            "candidates": candidates,
        }

    def retrieve_category(self, symptoms: dict, category: str, profile: dict = None,
                          top_k: int = CANDIDATES_PER_CATEGORY):
        """
        카테고리 하나에 대한 후보만 검색한다. 추천 본선이 쓰는 경로다.

        한 호출에 한 유형만 넣으면 LLM 이 비교할 대상이 모두 같은 유형이 되어
        '유형을 섞어라', '샴푸를 포함해라' 같은 제약을 프롬프트에 둘 필요가 없다.
        """
        profile = profile or {}
        levels = normalize_levels(symptoms)

        filters = {"category": category}
        if profile.get("max_price"):
            filters["max_price"] = int(profile["max_price"])
        if profile.get("exclude_product_ids"):
            filters["exclude_ids"] = list(profile["exclude_product_ids"])

        query_text = build_query(levels)
        qvec = self.embedder.encode([query_text])[0]

        # Hybrid 후보 검색
        # 1) 임베딩 유사도 상위 12개
        # 2) 위 12개에 없는 상품 중 성분 적합도 상위 3개 추가
        # 3) 성분 후보가 부족하면 임베딩 다음 순위 상품으로 채운다.
        final_k = max(1, int(top_k))
        embedding_k = min(HYBRID_EMBEDDING_K, final_k)
        ingredient_k = min(HYBRID_INGREDIENT_K, max(0, final_k - embedding_k))

        # 성분 후보가 부족할 때 채울 수 있도록 최종 개수만큼 임베딩 검색한다.
        embedding_all = self.store.search(qvec, top_k=final_k, **filters)
        embedding_candidates = embedding_all[:embedding_k]
        selected_ids = {c["product_id"] for c in embedding_candidates}

        ingredient_candidates = []
        if ingredient_k > 0 and any(levels.values()):
            scored = []
            exclude_ids = set(filters.get("exclude_ids") or [])
            max_price = filters.get("max_price")

            for rec in self.store.records:
                if rec.get("category") != category:
                    continue
                if rec.get("product_id") in selected_ids or rec.get("product_id") in exclude_ids:
                    continue

                price = rec.get("price")
                if max_price is not None and (price is None or price > max_price):
                    continue

                scores, _ = ingredient_scores(rec.get("ingredients", ""))
                ingredient_fit = sum(
                    float(scores.get(sym, 0) or 0) * float(level)
                    for sym, level in levels.items()
                    if level > 0
                )
                if ingredient_fit <= 0:
                    continue

                cand = dict(rec)
                vec = self.store.vector_of(cand["product_id"])
                cand["similarity"] = round(float(vec @ qvec), 4) if vec is not None else 0.0
                cand["ingredient_fit"] = round(ingredient_fit, 4)
                scored.append(cand)

            scored.sort(key=lambda c: (-c["ingredient_fit"], -c.get("similarity", 0)))
            ingredient_candidates = scored[:ingredient_k]

        candidates = embedding_candidates + ingredient_candidates
        selected_ids.update(c["product_id"] for c in ingredient_candidates)

        # 성분 후보가 3개보다 적으면 임베딩 13위 이후로 부족한 수를 채운다.
        if len(candidates) < final_k:
            for cand in embedding_all[embedding_k:]:
                if cand["product_id"] in selected_ids:
                    continue
                candidates.append(cand)
                selected_ids.add(cand["product_id"])
                if len(candidates) >= final_k:
                    break

        candidates = [self._annotate(c, profile) for c in candidates]
        for rank, c in enumerate(candidates, start=1):
            c["retrieval_rank"] = rank

        return {
            "category": category,
            "query": query_text,
            "levels": levels,
            "priority": ranked_symptoms(levels),
            "candidates": candidates,
        }

    # ── 후보 가공 ───────────────────────────────────────

    @staticmethod
    def _annotate(cand: dict, profile: dict) -> dict:
        """후보에 성분 점수를 계산해 붙인다.

        성분 점수는 인덱스에 저장해 두지 않고 여기서 매번 계산한다.
        선정된 후보의 전성분 문자열을 파싱하는 비용뿐이고,
        점수표를 수정해도 인덱스를 다시 만들 필요가 없다.

        알레르기는 지금 다루지 않는다.
        별도 모듈(Allergy RAG)에서 처리할 예정이고, 그전까지는 추천 경로에서 뺀다.
        한 LLM 에 추천과 알레르기 판정을 같이 시켰을 때
        '관련 성분이 없어 안전합니다' 라고 쓴 상품에 실제로는 매칭이 있는 경우가 나왔다.
        """
        cand = dict(cand)
        ingredients = cand.get("ingredients", "")
        scores, evidence = ingredient_scores(ingredients)
        cand["symptom_scores"] = scores
        cand["score_evidence"] = {k: v for k, v in evidence.items() if v}
        cand["active_ingredients"] = active_ingredients(ingredients)

        # 순한 정도. 증상이 모두 0단계인 사용자에게 쓰는 기준이다.
        g_score, g_absent, g_present = gentleness(ingredients)
        cand["gentleness"] = g_score
        cand["gentle_absent"] = g_absent
        cand["gentle_present"] = g_present
        return cand


if __name__ == "__main__":
    from recommendation.config import SYMPTOM_KR

    r = Retriever(backend="hashing")
    res = r.retrieve({"dandruff": 1, "hair_loss": 2},
                     profile={"age_group": "30대", "max_price": 50000})

    print("Query:", res["query"])
    print("우선순위:", [SYMPTOM_KR[s] for s in res["priority"]])
    print(f"후보 {len(res['candidates'])}개\n")
    for c in res["candidates"][:8]:
        sc = c["symptom_scores"]
        print(f"{c['retrieval_rank']:2d}. [{c['category']:9s}] {c['name_clean'][:34]:34s}"
              f" sim {c['similarity']:.3f}"
              f" | 탈모 {sc['hair_loss']:.1f} 비듬 {sc['dandruff']:.1f}"
              )
