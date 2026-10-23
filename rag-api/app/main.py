"""FastAPI demonstration for manual vision-model outputs, local CSV, RAG and Qwen."""
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import FileResponse
from app.schemas.request import RecommendRequest

from app.config import SYMPTOMS

app = FastAPI(title="MOVAR 두피 기반 상품 추천 데모", version="0.1")
POOL = ThreadPoolExecutor(max_workers=1)   # prevent simultaneous model overload
JOBS = {}
JOBS_LOCK = Lock()


@app.on_event("startup")
def sync_products_at_startup():
    # RAG 내부 상품 동기화만 실행. 기존 추천 API/검색/LLM 코드는 변경하지 않는다.
    from app.retrieval.supabase_sync import synchronize_products
    synchronize_products()


def require_demo_key(x_movar_demo_key: str | None = Header(default=None)):
    key = os.getenv("MOVAR_DEMO_KEY", "")
    if key and not secrets.compare_digest(x_movar_demo_key or "", key):
        raise HTTPException(401, "시연 접근키가 올바르지 않습니다.")


@lru_cache(maxsize=1)
def get_service():
    from app.services.recommendation_service import RecommendationService
    return RecommendationService()


def run_recommend(payload):
    service = get_service()
    data = payload.model_dump(exclude_none=True)
    return service.recommend(data["symptoms"], data.get("user_info"), plan=data.get("categories"), use_llm=True)


@app.get("/")
def home():
    return FileResponse(Path(__file__).resolve().parent.parent / "frontend" / "index.html")


@app.get("/health")
def health():
    return {"status": "running", "mode": "qwen2.5:14b", "symptoms": SYMPTOMS}


@app.post("/recommend")
def recommend(payload: RecommendRequest, _auth=Depends(require_demo_key)):
    """Synchronous endpoint for /docs. Long inference: use /jobs instead."""
    try:
        return run_recommend(payload)
    except Exception as exc:
        raise HTTPException(503, f"추천 처리 실패: {type(exc).__name__}: {exc}") from exc


@app.post("/jobs", status_code=202)
def start_job(payload: RecommendRequest, _auth=Depends(require_demo_key)):
    """202 + polling avoids the RunPod HTTP proxy long-response timeout."""
    with JOBS_LOCK:
        # Prevent demo server from accepting unlimited jobs.
        if sum(j["state"] in ("queued", "running") for j in JOBS.values()) >= 2:
            raise HTTPException(429, "추천 작업이 이미 진행 중입니다. 완료 후 다시 시도하세요.")
        if len(JOBS) > 100:
            finished = [key for key, val in JOBS.items() if val["state"] in ("done", "error")]
            for key in finished[:50]:
                del JOBS[key]
        job_id = str(uuid4())
        JOBS[job_id] = {"state": "queued"}

    def worker():
        with JOBS_LOCK:
            JOBS[job_id] = {"state": "running"}
        try:
            result = run_recommend(payload)
            record = {"state": "done", "result": result}
        except Exception as exc:
            record = {"state": "error", "error": f"{type(exc).__name__}: {exc}"}
        with JOBS_LOCK:
            JOBS[job_id] = record

    POOL.submit(worker)
    return {"job_id": job_id, "state": "queued"}


@app.get("/jobs/{job_id}")
def job_status(job_id: str, _auth=Depends(require_demo_key)):
    with JOBS_LOCK:
        result = JOBS.get(job_id)
        if result is None:
            raise HTTPException(404, "요청을 찾을 수 없습니다.")
        return dict(result)
