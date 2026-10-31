"""Ollama Qwen2.5 14B scoring: Test 5 JSON Schema / temperature=0.

Scores only; IDs and ranking are owned by Python. Fail visibly if Ollama fails.
"""
import json
import math
import requests
from app.config import OLLAMA_HOST, LLM_MODEL, LLM_TIMEOUT
from app.llm.test5_prompt import SYSTEM_PROMPT


class QwenScoringClient:
    def __init__(self, host=OLLAMA_HOST, model=LLM_MODEL, timeout=LLM_TIMEOUT):
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout

    def available(self):
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=6)
            response.raise_for_status()
            models = {m.get("name") or m.get("model") for m in response.json().get("models", [])}
            return (self.model in models, f"사용 가능: {self.model}" if self.model in models else f"Ollama에 {self.model} 모델이 없습니다: {sorted(models)}")
        except requests.RequestException as exc:
            return False, f"Ollama 접속 실패: {exc}"

    def score(self, prompt, candidate_count):
        keys = [f"C{i:02d}" for i in range(1, candidate_count + 1)]
        schema = {
            "type": "object",
            "properties": {"scores": {
                "type": "object",
                "properties": {key: {"type": "number", "minimum": 0, "maximum": 100} for key in keys},
                "required": keys,
                "additionalProperties": False,
            }},
            "required": ["scores"],
            "additionalProperties": False,
        }
        payload = {
            "model": self.model,
            "system": SYSTEM_PROMPT,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "format": schema,
            "keep_alive": "30m",
            "options": {"temperature": 0, "num_ctx": 16384, "num_predict": 512},
        }
        response = requests.post(f"{self.host}/api/generate", json=payload, timeout=self.timeout)
        response.raise_for_status()
        raw = response.json().get("response", "")
        parsed = json.loads(raw)
        scores = parsed.get("scores") if isinstance(parsed, dict) else None
        if not isinstance(scores, dict) or set(scores.keys()) != set(keys):
            raise ValueError("Qwen이 요청한 후보 전체의 점수를 반환하지 않았습니다.")
        checked = {}
        for key in keys:
            value = scores[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{key} 점수 형식 오류: {value!r}")
            if not math.isfinite(float(value)) or not 0 <= float(value) <= 100:
                raise ValueError(f"{key} 점수 범위 오류: {value!r}")
            checked[key] = float(value)
        return checked
