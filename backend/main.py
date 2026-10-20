"""MOVAR backend entry point. Run from the backend directory."""

from typing import Literal

from fastapi import Body, Depends, FastAPI, File, Form, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from auth import get_current_user
from database import read_products
from hospitals import HospitalList, search_hospitals
from mock_ai import build_mock_request
from pipeline import AnalysisReportResponse, Category, analysis_report, parse_questionnaire
from recommend import RecommendRequest, RecommendResponse, recommend_products
from report import ReportRequest, ReportResponse, generate_report
from vision import MAX_UPLOAD_BYTES, AnalysisResponse, analyze_image

app = FastAPI(
    title="MOVAR Backend API",
    version="0.1.0",
    description="백엔드 상태 및 Supabase DB 연결 확인 API입니다. AI 연동은 아직 구현되지 않았습니다.",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
    allow_methods=['GET', 'POST'],
    allow_headers=['Authorization', 'Content-Type'],
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


@app.get('/me', tags=['인증'], summary='로그인 토큰(JWT) 검증 확인')
async def me(user: dict = Depends(get_current_user)):
    return user


@app.post('/recommendations', response_model=RecommendResponse, tags=['추천'], summary='두피 증상 기반 상품 추천 (추천 모델 서버 연동)')
async def create_recommendations(req: RecommendRequest):
    """팀 추천 모델 서버(RunPod)에 작업을 등록하고 완료될 때까지 기다린 뒤 추천 상품(최대 3개)을 반환합니다. 보통 수 초가 걸립니다."""
    return await recommend_products(req)


@app.post('/scalp-analyses', response_model=AnalysisResponse, tags=['분석'], summary='두피 사진으로 증상 6개 단계 분석 (이미지 모델 서버 연동)')
async def scalp_analysis(file: UploadFile = File(..., description='두피 사진 1장 (JPEG, PNG, WEBP, 10MB 이하)')):
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    return await analyze_image(content)


@app.post('/analysis-reports', response_model=AnalysisReportResponse, tags=['분석'], summary='사진 한 장으로 분석 → 제품 추천 → LLM 리포트까지 한 번에 생성')
async def create_analysis_report(
    file: UploadFile = File(..., description='두피 사진 1장 (JPEG, PNG, WEBP, 10MB 이하)'),
    categories: list[Category] = Form(['shampoo'], description='추천 카테고리 (여러 번 지정 가능)'),
    questionnaire: str | None = Form(None, description='문진 답변 JSON 문자열. 예: {"세정 빈도": "하루 한 번"}'),
):
    parsed = parse_questionnaire(questionnaire)
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    return await analysis_report(content, categories, parsed)


@app.post('/reports', response_model=ReportResponse, tags=['리포트'], summary='분석 결과로 LLM 리포트 생성')
async def create_report(req: ReportRequest):
    return await generate_report(req)


@app.post('/reports/mock', response_model=ReportResponse, tags=['리포트'], summary='[목업] 가짜 AI 분석·추천 결과로 리포트 생성')
async def create_mock_report(questionnaire: dict[str, str] = Body(default_factory=dict)):
    """AI 모델이 완성되기 전 흐름 확인용입니다. 두피 분석과 제품 추천은 목업 값이며 LLM 문구만 실제 생성됩니다."""
    return await generate_report(await build_mock_request(questionnaire))


@app.get('/hospitals', response_model=HospitalList, tags=['병원'], summary='현재 위치 기준 주변 병원 검색')
async def hospitals(
    lat: float = Query(..., ge=-90, le=90, description='위도'),
    lng: float = Query(..., ge=-180, le=180, description='경도'),
    radius: int = Query(5000, ge=100, le=20000, description='검색 반경(m)'),
    query: Literal['피부과', '탈모'] = Query('피부과', description='검색 키워드'),
    size: int = Query(15, ge=1, le=15),
):
    return await search_hospitals(lat, lng, radius, query, size)


@app.get('/products', tags=['제품'], summary='DB 연결 검증용 제품 목록 조회')
async def products(limit: int = Query(10, ge=1, le=100)):
    rows, total = await read_products(limit)
    return {'items': rows, 'total': total}
