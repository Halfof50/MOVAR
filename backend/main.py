"""MOVAR backend entry point. Run from the backend directory."""

from fastapi import FastAPI, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from database import read_products

app = FastAPI(
    title="MOVAR Backend API",
    version="0.1.0",
    description="백엔드 상태 및 Supabase DB 연결 확인 API입니다. AI 연동은 아직 구현되지 않았습니다.",
)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health", response_model=HealthResponse, tags=["상태"], summary="백엔드 서버 실행 상태 확인")
def health():
    """서버 실행 여부만 확인합니다. DB 및 외부 서비스 연결 검사는 포함하지 않습니다."""
    return HealthResponse(status="ok", service="movar-backend", version=app.version)


@app.get('/health/db', tags=['상태'], summary='실제 Supabase DB 조회로 연결 확인')
async def database_health():
    _, total = await read_products()
    return {'status': 'ok', 'database': 'connected', 'products_count': total}


@app.get('/products', tags=['제품'], summary='DB 연결 검증용 제품 목록 조회')
async def products(limit: int = Query(10, ge=1, le=100)):
    rows, total = await read_products(limit)
    return {'items': rows, 'total': total}
