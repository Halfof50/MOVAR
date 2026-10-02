"""
공통 설정

경로와 모델 이름만 모아둔다. 값을 바꿀 때 코드를 찾아다니지 않도록.
환경변수가 있으면 환경변수를 우선한다.
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ── 데이터 ──────────────────────────────────────────────
DATA_DIR    = ROOT / "data"
PRODUCTS_CSV = Path(os.getenv("MOVAR_PRODUCTS_CSV", DATA_DIR / "products.csv"))
INDEX_DIR   = Path(os.getenv("MOVAR_INDEX_DIR", DATA_DIR / "index"))

# ── 증상 ────────────────────────────────────────────────
SYMPTOMS = ["micro_keratin", "excess_sebum", "follicular_erythema",
            "follicular_pustule", "dandruff", "hair_loss"]

SYMPTOM_KR = {
    "micro_keratin":       "미세각질",
    "excess_sebum":        "피지과다",
    "follicular_erythema": "모낭사이홍반",
    "follicular_pustule":  "모낭홍반농포",
    "dandruff":            "비듬",
    "hair_loss":           "탈모",
}

LEVEL_KR = {0: "없음", 1: "경증", 2: "중등도", 3: "중증"}

CATEGORY_KR = {
    "shampoo":   "샴푸",
    "scaler":    "스케일러",
    "treatment": "트리트먼트",
    "tonic":     "토닉",
}

# ── Document 구성 ───────────────────────────────────────
# 검색용 Document 에 넣을 줄. 어느 줄이 검색에 실제로 기여하는지 비교하기 위해 토글로 둔다.
# ablation.py 가 이 값을 바꿔가며 인덱스를 만들고 커버리지를 비교한다.
DOC_PART_NAMES = ["name", "category", "spec", "actives", "purpose"]
DOC_PARTS = set(
    (os.getenv("MOVAR_DOC_PARTS") or ",".join(DOC_PART_NAMES)).replace(" ", "").split(",")
)

# ── 임베딩 ──────────────────────────────────────────────
EMBED_MODEL = os.getenv("MOVAR_EMBED_MODEL", "jhgan/ko-sroberta-multitask")
EMBED_DIM   = 768

# ── 검색 ────────────────────────────────────────────────
TOP_K = int(os.getenv("MOVAR_TOP_K", "15"))

# 평가 스크립트에서 쓰는 카테고리별 할당량 (혼합 검색용).
# 추천 본선에서는 쓰지 않는다.
CATEGORY_QUOTA = {"shampoo": 6, "scaler": 4, "treatment": 4, "tonic": 4}

# ── 카테고리 단위 추천 ──────────────────────────────────
# 한 번의 LLM 호출에 한 카테고리만 넣는다.
# 여러 유형을 추천해야 하면 카테고리 수만큼 호출한다.
#
# 이렇게 하면 프롬프트에서 규칙 4개가 사라진다.
#   '샴푸 최소 1개 포함'      → 샴푸 호출에서는 전부 샴푸라 불필요
#   '같은 카테고리 중복 금지'   → 구조적으로 불가능
#   '서로 다른 유형을 섞기'     → 호출 단위로 보장
#   '개수 3~5 중 몇 개'       → 3개로 고정
# 비교 대상이 모두 같은 유형이어서 모델은 증상 적합도만 비교하면 된다.
CANDIDATES_PER_CATEGORY = int(os.getenv("MOVAR_CANDIDATES_PER_CATEGORY", "12"))
PICK_PER_CATEGORY = int(os.getenv("MOVAR_PICK_PER_CATEGORY", "3"))

# 후보를 유사도 순으로 넣으면 모델이 그 순서를 정답으로 받아들이는 경향이 있다.
# 섞어서 넣으면 앞자리 선호가 품질 저하가 아니라 무작위로 바뀐다.
# 기본값은 끔. 실제로 앞에서만 고르는 현상이 보이면 켜서 비교한다.
SHUFFLE_CANDIDATES = os.getenv("MOVAR_SHUFFLE_CANDIDATES", "0") == "1"

# 리포트의 product_plan.combo 가 없을 때 코드가 카테고리를 정하는 규칙.
# (증상 key, 최소 레벨) 조건을 만족하면 그 카테고리를 넣는다. 샴푸는 항상.
FALLBACK_PLAN_RULES = [
    ("scaler",    [("micro_keratin", 2), ("excess_sebum", 2)]),
    ("tonic",     [("hair_loss", 2)]),
    ("treatment", [("follicular_erythema", 2), ("follicular_pustule", 2)]),
]
MAX_CATEGORIES = int(os.getenv("MOVAR_MAX_CATEGORIES", "3"))
CATEGORY_ORDER = ["shampoo", "scaler", "treatment", "tonic"]

# ── 로컬 LLM ────────────────────────────────────────────
OLLAMA_HOST  = os.getenv("OLLAMA_HOST", "http://localhost:11434")
LLM_MODEL    = os.getenv("MOVAR_LLM_MODEL", "llama3.1:8b-instruct-q4_K_M")
LLM_TIMEOUT  = int(os.getenv("MOVAR_LLM_TIMEOUT", "180"))

# 최종 추천 개수
FINAL_MIN = 3
FINAL_MAX = 5
