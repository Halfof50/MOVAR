"""One-shot flow: photo -> symptoms (vision model) -> product recommendation (RAG model) -> LLM report."""
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError

from questionnaire import Answers, to_report_answers, to_user_info
from recommend import RecommendedProduct, RecommendRequest, recommend_products
from report import ProductInput, ReportRequest, ReportResponse, generate_report
from vision import analyze_image

Category = Literal['shampoo', 'scaler', 'treatment', 'tonic']


class AnalysisReportResponse(BaseModel):
    symptoms: dict[str, int]
    recommendations: list[RecommendedProduct]
    report: ReportResponse
    analysis_id: int | None = None


async def analysis_report(content: bytes, categories: list[Category], answers: Answers) -> AnalysisReportResponse:
    analysis = await analyze_image(content)
    recommended = await recommend_products(
        RecommendRequest(symptoms=analysis.symptoms, categories=categories, user_info=to_user_info(answers)),
    )

    # Fit the recommended products into the report input; the report is written only for these.
    products = [
        ProductInput(product_id=p.product_id, product_name=p.product_name[:200], brand_name=p.brand[:100] if p.brand else None)
        for p in recommended.recommendations
    ]
    try:
        report_request = ReportRequest(symptoms=analysis.symptoms, questionnaire=to_report_answers(answers), products=products)
    except ValidationError:
        raise HTTPException(422, {'code': 'QUESTIONNAIRE_INVALID', 'message': '문진 문항과 답변이 너무 깁니다.'}) from None

    return AnalysisReportResponse(
        symptoms=analysis.symptoms.model_dump(),
        recommendations=recommended.recommendations,
        report=await generate_report(report_request),
    )
