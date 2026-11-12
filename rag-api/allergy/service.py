# -*- coding: utf-8 -*-
"""기존 상품 추천 결과 TOP3의 ID만 받아 알레르기 관련 원료 여부를 평가한다.

추천 순위/선정 결과/상품 metadata에는 관여하지 않는다. DB는 기존 products.csv를 읽기 전용으로 사용한다.
"""
from __future__ import annotations
import csv
import logging
import os
from functools import lru_cache
from pathlib import Path
import re
from typing import Any
from allergy.retriever import AllergyKB, EMBED_MODEL
from allergy.prompt import make_context
from allergy.llm_client import AllergyLLMClient

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
ALLERGY_DB = Path(__file__).resolve().parent / "data" / "allergy_knowledge.csv"
PRODUCTS_CSV = ROOT / "data" / "products.csv"


def normalize_allergies(value: list[str] | str | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        value = re.split(r"[,，;；\n]+", value)
    if not isinstance(value, (list, tuple)):
        raise ValueError("allergies는 문자열 또는 문자열 배열이어야 합니다")
    items = list(dict.fromkeys(str(x).strip() for x in value if str(x).strip()))
    if len(items) > 8 or any(len(x) > 100 for x in items):
        raise ValueError("알레르기 입력은 최대 8개, 항목당 100자 이하")
    return items


class AllergyService:
    def __init__(self, db_path: Path = ALLERGY_DB, products_path: Path = PRODUCTS_CSV,
                 client: AllergyLLMClient | None = None, use_embedding: bool = False):
        self.products_path = Path(products_path)
        db_path = Path(db_path)
        self.kb = AllergyKB(db_path, db_path.parent / "index", use_embedding, EMBED_MODEL)
        self.client = client if client is not None else AllergyLLMClient(
            host=os.getenv("ALLERGY_OLLAMA_HOST", os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")),
            model=os.getenv("ALLERGY_LLM_MODEL", os.getenv("MOVAR_LLM_MODEL", "qwen2.5:14b")),
            timeout=int(os.getenv("ALLERGY_LLM_TIMEOUT", "300")),
            num_ctx=int(os.getenv("ALLERGY_NUM_CTX", "8192")),
            num_predict=int(os.getenv("ALLERGY_NUM_PREDICT", "800")))
        self._catalog: dict[str, dict[str, str]] | None = None
        self._catalog_mtime_ns: int | None = None

    def _catalog_items(self) -> dict[str, dict[str, str]]:
        # 상품 DB를 새로 만들지 않는다. 기존 CSV를 읽고 변경 시에만 재로드.
        stat = self.products_path.stat()
        if self._catalog is None or self._catalog_mtime_ns != stat.st_mtime_ns:
            with self.products_path.open("r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            if not rows or not {"product_id", "ingredients"}.issubset(rows[0]):
                raise ValueError("상품 DB에 product_id / ingredients 컬럼 필요")
            self._catalog = {str(r["product_id"]).strip(): r for r in rows}
            self._catalog_mtime_ns = stat.st_mtime_ns
        return self._catalog

    def assess(self, top3: list[dict[str, Any]], allergies: list[str] | str | None) -> dict[str, bool | None]:
        """TOP3에서 상품 ID만 추출, 기존 CSV 전성분 조회, 판별 결과만 반환.

        오류/불확실을 절대 false로 대체하지 않는다. 실패 시 null로 반환한다.
        """
        if len(top3) > 3:
            raise ValueError("알레르기 검사 입력은 최종 TOP3까지만 허용")
        ids = [str(p["product_id"]) for p in top3]
        if len(ids) != len(set(ids)):
            raise ValueError("최종 TOP3 상품 ID 중복")
        fallback = dict.fromkeys(ids, None)
        user_allergies = normalize_allergies(allergies)
        if not ids or not user_allergies:
            return fallback
        try:
            catalog = self._catalog_items()
            products = []
            for rec in top3:
                pid = str(rec["product_id"])
                src = catalog.get(pid)
                if src is None:
                    raise ValueError(f"상품 DB에 product_id={pid} 없음")
                ingredients = str(src.get("ingredients") or "").strip()
                if not ingredients:
                    raise ValueError(f"상품 DB의 product_id={pid} 전성분 누락")
                products.append({"product_id": pid,
                                 "product_name": str(src.get("name_clean") or src.get("name") or src.get("product_name") or ""),
                                 "ingredients": ingredients})
            context, diagnostic = make_context(self.kb, user_allergies, products)
            # 알레르기명 자체가 DB에서 전혀 검증되지 않은 경우에는 안전을 암시할 수 있는 false를 방지.
            if all(v["status"] != "exact" for v in diagnostic.values()):
                logger.warning("알레르기 DB 미등록 입력: %s", user_allergies)
                return fallback
            result = self.client.predict(user_allergies, products, context)
            # LLM 반환값은 검증한 JSON true/false/null만 허용.
            return {pid: result[pid] for pid in ids}
        except Exception as exc:
            logger.warning("알레르기 판별 보류(추천 결과는 유지): %s: %s", type(exc).__name__, exc)
            return fallback


@lru_cache(maxsize=1)
def get_allergy_service() -> AllergyService:
    # 동일한 FastAPI 프로세스 내에서 Lazy Initialize: 별도 서버 실행 불필요.
    use_embedding = os.getenv("ALLERGY_USE_EMBEDDING", "0").lower() in ("1", "true", "yes")
    return AllergyService(use_embedding=use_embedding)


def attach_allergy_to_top3(top3: list[dict[str, Any]], allergies: list[str] | str | None,
                           service: AllergyService | None = None) -> list[dict[str, Any]]:
    """기존 추천 순위/상품 선정은 변경하지 않고 allergy_risk만 추가한다.

    호출 위치: LLM의 TOP3 최종 확정 후, 상품 부가정보 결합 전.
    """
    if not top3:
        return top3
    if not allergies:
        risks = {str(rec["product_id"]): None for rec in top3}
    else:
        try:
            risks = (service or get_allergy_service()).assess(top3, allergies)
        except Exception as exc:
            logger.warning("알레르기 서비스 초기화 실패: %s", exc)
            risks = {str(rec["product_id"]): None for rec in top3}
    for rec in top3:
        rec["allergy_risk"] = risks.get(str(rec["product_id"]))
    return top3
