"""
로컬 LLM 호출 (Ollama)

Ollama 를 띄워 두고 HTTP 로 호출한다. 모델 가중치는 받아서 그대로 쓴다.

    ollama serve
    ollama pull llama3.1:8b-instruct-q4_K_M

format="json" 을 주면 Ollama 가 JSON 문법에 맞는 토큰만 생성하도록 제약한다.
형식이 깨진 응답을 재시도로 메우는 경로를 줄일 수 있다.

temperature 는 0.2 로 둔다.
같은 입력에 추천이 매번 흔들리면 결과를 설명할 수 없고,
0 으로 고정하면 표현이 기계적으로 반복된다.
"""

import json

import requests

from recommendation.config import LLM_MODEL, LLM_TIMEOUT, OLLAMA_HOST


class LlamaClient:

    def __init__(self, host=OLLAMA_HOST, model=LLM_MODEL, timeout=LLM_TIMEOUT):
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout

    # ── 상태 확인 ───────────────────────────────────────

    def available(self):
        """(가능 여부, 메시지). 서비스 실행 여부와 모델 설치 여부를 함께 본다."""
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=5)
            r.raise_for_status()
        except Exception as e:
            return False, (f"Ollama 에 연결할 수 없습니다 ({self.host}). "
                           f"{type(e).__name__}: {e}\n'ollama serve' 실행 여부를 확인하십시오.")
        names = [m.get("name", "") for m in r.json().get("models", [])]
        if not any(n == self.model or n.startswith(self.model.split(":")[0]) for n in names):
            return False, (f"모델 '{self.model}' 이 없습니다. 설치된 모델: {names}\n"
                           f"'ollama pull {self.model}' 로 받으십시오.")
        return True, f"사용 가능: {self.model}"

    # ── 생성 ────────────────────────────────────────────

    def generate_json(self, prompt: str, temperature=0.0, num_ctx=8192,
                      num_predict=1024, retries=1, seed=0):
        """
        프롬프트 → dict

        JSON 파싱에 실패하면 retries 횟수만큼 다시 호출한다.
        끝까지 실패하면 예외를 올려 service 가 폴백을 쓰게 한다.

        temperature 와 seed 를 고정하는 이유.
            같은 입력에 매번 다른 상품이 나오면 추천 근거를 설명할 수 없다.
            temperature 0.2 로 두고 측정했을 때 같은 입력을 두 번 돌리면
            3개 중 1개가 바뀌었고, 어떤 경우는 3개 중 2개가 바뀌었다.
            설계 원칙에도 '랜덤 추천은 사용하지 않는다' 고 적혀 있다.

        GPU 연산 순서 때문에 완전한 결정론은 아니지만, 흔들림은 크게 줄어든다.
        """
        last_err = None
        for attempt in range(retries + 1):
            raw = self._call(prompt, temperature, num_ctx, num_predict, seed)
            try:
                return json.loads(raw)
            except json.JSONDecodeError as e:
                last_err = e
                salvaged = _extract_json(raw)
                if salvaged is not None:
                    return salvaged
        raise ValueError(f"LLM 응답을 JSON 으로 읽지 못했습니다: {last_err}")

    def _call(self, prompt, temperature, num_ctx, num_predict, seed=0) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": temperature,
                "seed": seed,
                "num_ctx": num_ctx,
                "num_predict": num_predict,
                "repeat_penalty": 1.05,
            },
        }
        r = requests.post(f"{self.host}/api/generate", json=payload, timeout=self.timeout)
        r.raise_for_status()
        return r.json().get("response", "")


def _extract_json(text: str):
    """코드 블록이나 앞뒤 설명이 섞여 온 경우 중괄호 구간만 떼어 본다."""
    s = str(text)
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(s[start:end + 1])
    except json.JSONDecodeError:
        return None


if __name__ == "__main__":
    c = LlamaClient()
    ok, msg = c.available()
    print(msg)
    if ok:
        out = c.generate_json(
            '{"answer": 숫자} 형식으로만 답한다. 1 더하기 1은?')
        print(out)
