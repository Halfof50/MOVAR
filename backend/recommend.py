"""Product recommendation via the team's RAG API (RunPod): submit a job, then poll until it is done."""
import asyncio
import os
import time
from pathlib import Path
from typing import Annotated, Literal

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError

POLL_INTERVAL = 2.0
JOB_DEADLINE = 120.0

Level = Annotated[int, Field(ge=0, le=3, description='증상 단계 0(없음)~3(가장 높음)')]

SYMPTOM_LABELS = {
    'micro_keratin': '미세각질',
    'excess_sebum': '피지과다',
    'follicular_erythema': '모낭사이홍반',
    'follicular_pustule': '모낭홍반농포',
    'dandruff': '비듬',
    'hair_loss': '탈모',
}


# ---- request ----------------------------------------------------------------

class Symptoms(BaseModel):
    micro_keratin: Level
    excess_sebum: Level
    follicular_erythema: Level
    follicular_pustule: Level
    dandruff: Level
    hair_loss: Level


class UserInfo(BaseModel):
    age_group: str | None = Field(None, max_length=20, examples=['20대'])
    wash_frequency: str | None = Field(None, max_length=20, examples=['하루 1회'])
    max_price: int | None = Field(None, gt=0, description='최대 희망 가격(원)')


class RecommendRequest(BaseModel):
    symptoms: Symptoms
    categories: list[Literal['shampoo', 'scaler', 'treatment', 'tonic']] = Field(
        min_length=1, max_length=4, description='추천 카테고리. 선택한 전체에서 합쳐 최대 3개가 추천된다.',
    )
    user_info: UserInfo | None = None


# ---- response ---------------------------------------------------------------

class RecommendedProduct(BaseModel):
    rank: int
    product_id: int
    product_name: str
    brand: str | None = None
    category: str | None = None
    category_kr: str | None = None
    price: int | float | None = None
    rating: int | float | None = None
    reviews: int | None = None
    image: str | None = None
    link: str | None = None
    volume: str | None = None
    reason: str | None = None
    matched_symptoms: list[str] = Field(default_factory=list)


class RecommendResponse(BaseModel):
    recommendations: list[RecommendedProduct]
    priority: list[str]


# ---- client -----------------------------------------------------------------

def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {'code': code, 'message': message})


def _check(response: httpx.Response) -> None:
    if response.status_code == 429:
        raise _error(429, 'RECOMMEND_BUSY', '추천 요청이 많습니다. 잠시 후 다시 시도해 주세요.')
    if response.status_code == 422:
        raise _error(502, 'RECOMMEND_UPSTREAM_ERROR', '추천 서버가 요청 형식을 받아들이지 않았습니다.')
    if response.status_code >= 400:
        raise _error(503, 'RECOMMEND_UPSTREAM_ERROR', '추천 서버 호출에 실패했습니다.')


def _invalid() -> HTTPException:
    return _error(502, 'RECOMMEND_INVALID_RESPONSE', '추천 서버 응답 형식이 올바르지 않습니다.')


async def _submit(client: httpx.AsyncClient, base: str, payload: dict) -> str:
    response = await client.post(f'{base}/jobs', json=payload)
    _check(response)
    try:
        return str(response.json()['job_id'])
    except (ValueError, KeyError, TypeError):
        raise _invalid() from None


async def _wait(client: httpx.AsyncClient, base: str, job_id: str) -> dict:
    deadline = time.monotonic() + JOB_DEADLINE
    while time.monotonic() < deadline:
        response = await client.get(f'{base}/jobs/{job_id}')
        if response.status_code == 404:
            raise _error(502, 'RECOMMEND_JOB_LOST', '추천 작업을 찾을 수 없습니다. 추천 서버가 재시작되었을 수 있습니다.')
        _check(response)
        try:
            job = response.json()
            state = job['state']
        except (ValueError, KeyError, TypeError):
            raise _invalid() from None
        if state == 'done':
            return job
        if state == 'error':
            raise _error(502, 'RECOMMEND_JOB_FAILED', '추천 작업이 실패했습니다.')
        await asyncio.sleep(POLL_INTERVAL)
    raise _error(504, 'RECOMMEND_TIMEOUT', '추천 응답 대기 시간이 초과되었습니다.')


async def recommend_products(req: RecommendRequest) -> RecommendResponse:
    load_dotenv(Path(__file__).with_name('.env'))
    base = os.getenv('MOVAR_API_BASE_URL', '').rstrip('/')
    if not base:
        raise _error(503, 'RECOMMEND_NOT_CONFIGURED', '추천 서버 설정이 필요합니다.')

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            job_id = await _submit(client, base, req.model_dump(exclude_none=True))
            job = await _wait(client, base, job_id)
    except httpx.TimeoutException:
        raise _error(504, 'RECOMMEND_TIMEOUT', '추천 서버 응답 시간이 초과되었습니다.') from None
    except httpx.RequestError:
        raise _error(503, 'RECOMMEND_UNREACHABLE', '추천 서버에 접속할 수 없습니다. 서버가 꺼져 있을 수 있습니다.') from None

    try:
        result = job['result']
        return RecommendResponse(
            recommendations=[RecommendedProduct.model_validate(p) for p in result['recommendations']],
            priority=result.get('priority', []),
        )
    except (KeyError, TypeError, ValidationError):
        raise _invalid() from None
