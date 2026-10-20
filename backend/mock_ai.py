"""MOCK stand-ins for the AI models still in development. Replace with real model calls later."""
from database import read_products
from pipeline import AnalysisReportResponse
from recommend import RecommendedProduct, Symptoms
from report import ProductInput, ReportRequest, generate_report


async def analyze_scalp() -> tuple[int, Symptoms]:
    """MOCK scalp analysis: fixed sample result (care score and the six symptom levels)."""
    return 76, Symptoms(
        micro_keratin=0, excess_sebum=2, follicular_erythema=1,
        follicular_pustule=0, dandruff=0, hair_loss=0,
    )


async def recommend_products(limit: int = 2) -> list[ProductInput]:
    """MOCK recommendation: the first products in the DB, not a personalized result."""
    rows, _ = await read_products(limit)
    return [ProductInput(product_id=r['product_id'], product_name=r['product_name'], brand_name=r.get('brand_name')) for r in rows]


async def build_mock_request(questionnaire: dict[str, str]) -> ReportRequest:
    care_score, symptoms = await analyze_scalp()
    return ReportRequest(
        symptoms=symptoms,
        care_score=care_score,
        questionnaire=questionnaire,
        products=await recommend_products(),
    )


async def build_mock_analysis(questionnaire: dict[str, str]) -> AnalysisReportResponse:
    """MOCK full result in the same shape as POST /analysis-reports, for trying the dashboard and history."""
    request = await build_mock_request(questionnaire)
    return AnalysisReportResponse(
        symptoms=request.symptoms.model_dump(),
        recommendations=[
            RecommendedProduct(rank=rank, product_id=p.product_id, product_name=p.product_name, brand=p.brand_name)
            for rank, p in enumerate(request.products, start=1)
        ],
        report=await generate_report(request),
    )
