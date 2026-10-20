"""Dashboard and change history over past analyses.

TEMPORARY STORAGE: analyses are kept in server memory only, so they disappear when the server restarts.
Guests (no token) share one record list. Replace `save` / `list_for` with DB access once the tables in DB_SPEC.md exist.
"""
from itertools import count

from fastapi import HTTPException
from pydantic import BaseModel

from pipeline import AnalysisReportResponse
from recommend import SYMPTOM_LABELS, RecommendedProduct
from report import ReportResponse

GUEST = 'guest'
MAX_PER_OWNER = 50

_ids = count(1)
_store: dict[str, list['StoredAnalysis']] = {}  # owner -> analyses, oldest first


class StoredAnalysis(BaseModel):
    analysis_id: int
    analyzed_at: str
    care_score: int | None
    symptoms: dict[str, int]
    recommendations: list[RecommendedProduct]
    report: ReportResponse


class Condition(BaseModel):
    code: str
    label: str
    level: int


class DashboardUser(BaseModel):
    is_guest: bool
    nickname: str | None


class LatestAnalysis(BaseModel):
    analysis_id: int
    analyzed_at: str
    care_score: int | None
    summary_title: str
    summary_text: str
    conditions: list[Condition]


class Dashboard(BaseModel):
    user: DashboardUser
    latest_analysis: LatestAnalysis | None
    recommended_products: list[RecommendedProduct]


class HistoryItem(BaseModel):
    analysis_id: int
    analyzed_at: str
    care_score: int | None
    symptoms: dict[str, int]
    headline: str
    changes: dict[str, int] | None  # level now minus level in the previous analysis; None for the oldest


class HistoryList(BaseModel):
    items: list[HistoryItem]
    total: int


def owner_key(user: dict | None) -> str:
    return user['id'] if user else GUEST


def save(owner: str, result: AnalysisReportResponse) -> StoredAnalysis:
    stored = StoredAnalysis(
        analysis_id=next(_ids),
        analyzed_at=result.report.analyzed_at,
        care_score=result.report.care_score,
        symptoms=result.symptoms,
        recommendations=result.recommendations,
        report=result.report,
    )
    records = _store.setdefault(owner, [])
    records.append(stored)
    del records[:-MAX_PER_OWNER]
    return stored


def list_for(owner: str) -> list[StoredAnalysis]:
    """Oldest first."""
    return _store.get(owner, [])


def get_one(owner: str, analysis_id: int) -> StoredAnalysis:
    for record in list_for(owner):
        if record.analysis_id == analysis_id:
            return record
    raise HTTPException(404, {'code': 'ANALYSIS_NOT_FOUND', 'message': '분석 기록을 찾을 수 없습니다.'})


def build_dashboard(user: dict | None) -> Dashboard:
    records = list_for(owner_key(user))
    nickname = user['email'].split('@')[0] if user and user.get('email') else None
    dashboard_user = DashboardUser(is_guest=user is None, nickname=nickname)
    if not records:
        return Dashboard(user=dashboard_user, latest_analysis=None, recommended_products=[])

    latest = records[-1]
    return Dashboard(
        user=dashboard_user,
        latest_analysis=LatestAnalysis(
            analysis_id=latest.analysis_id,
            analyzed_at=latest.analyzed_at,
            care_score=latest.care_score,
            summary_title=latest.report.headline,
            summary_text=latest.report.headline_text,
            conditions=[Condition(code=code, label=label, level=latest.symptoms[code]) for code, label in SYMPTOM_LABELS.items()],
        ),
        recommended_products=latest.recommendations,
    )


def build_history(user: dict | None, limit: int) -> HistoryList:
    records = list_for(owner_key(user))
    items = []
    for index, record in enumerate(records):
        previous = records[index - 1].symptoms if index else None
        items.append(HistoryItem(
            analysis_id=record.analysis_id,
            analyzed_at=record.analyzed_at,
            care_score=record.care_score,
            symptoms=record.symptoms,
            headline=record.report.headline,
            changes={code: record.symptoms[code] - previous[code] for code in SYMPTOM_LABELS} if previous else None,
        ))
    items.reverse()  # newest first
    return HistoryList(items=items[:limit], total=len(items))
