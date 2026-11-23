# -*- coding: utf-8 -*-
"""Ollama 호출 및 기존 테스트와 동일한 JSON/상품 ID 검증."""
from __future__ import annotations
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from allergy.prompt import build_request

def parse_result(raw: str, ids: list[str]):
    try:
        s = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
        s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s).strip()
        obj = json.loads(s)
        if not isinstance(obj, dict) or not isinstance(obj.get("results"), list):
            raise ValueError("JSON results 배열 없음")
        rows = obj["results"]
        parsed = {}
        ordered = []
        for entry in rows:
            if not isinstance(entry, dict) or "product_id" not in entry:
                raise ValueError("결과 항목 구조 오류")
            pid = str(entry["product_id"])
            if pid in parsed or pid not in ids:
                raise ValueError("상품 ID 중복/후보 외 상품")
            value = entry.get("allergy_risk", "invalid")
            if value is not None and type(value) is not bool:
                raise ValueError("allergy_risk는 JSON true/false/null 이어야 함")
            parsed[pid] = value
            ordered.append(pid)
        return parsed, ordered == ids and set(parsed) == set(ids), ""
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        return {}, False, str(exc)


def parse_result_allow_reorder(raw: str, ids: list[str]):
    """정확한 ID 집합+JSON 타입을 검사. 원본 ID 순서 위반은 별도 진단한다."""
    parsed, original_valid, error = parse_result(raw, ids)
    complete = not error and len(parsed) == len(ids) and set(parsed) == set(ids)
    order_preserved = bool(complete and list(parsed) == ids)
    return parsed, bool(complete), error, order_preserved

class AllergyLLMClient:
    def __init__(self, *, host: str = "http://127.0.0.1:11434", model: str = "qwen2.5:14b",
                 timeout: int = 300, num_ctx: int = 8192, num_predict: int = 800):
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.num_ctx = num_ctx
        self.num_predict = num_predict

    def predict(self, allergies: list[str], products: list[dict], rag_context: dict) -> dict[str, bool | None]:
        if not products:
            return {}
        ids = [str(p["product_id"]) for p in products]
        if len(ids) != len(set(ids)):
            raise ValueError("중복된 상품 ID")
        payload = build_request(self.model, allergies, products, rag_context,
                                self.num_ctx, self.num_predict)
        req = Request(self.host + "/api/chat", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=self.timeout) as resp:
            answer = json.loads(resp.read().decode("utf-8"))
        content = answer.get("message", {}).get("content", "")
        parsed, complete, error, _order_preserved = parse_result_allow_reorder(content, ids)
        if not complete:
            raise ValueError("알레르기 LLM 응답 오류: " + (error or "상품 ID 누락/중복"))
        return parsed
