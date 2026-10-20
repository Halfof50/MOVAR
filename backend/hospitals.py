"""Nearby hospital search via the Kakao Local API. The REST API key never leaves the server."""
import os
from pathlib import Path
from typing import Literal

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException
from pydantic import BaseModel

KAKAO_KEYWORD_URL = 'https://dapi.kakao.com/v2/local/search/keyword.json'


class Hospital(BaseModel):
    name: str
    category: str | None
    address: str | None
    road_address: str | None
    phone: str | None
    distance_m: int | None
    lat: float
    lng: float
    place_url: str | None


class HospitalList(BaseModel):
    items: list[Hospital]
    total: int


def _clean(value: str | None) -> str | None:
    return value or None


async def search_hospitals(lat: float, lng: float, radius: int, query: Literal['피부과', '탈모'], size: int) -> HospitalList:
    load_dotenv(Path(__file__).with_name('.env'))
    key = os.getenv('KAKAO_REST_API_KEY', '')
    if not key:
        raise HTTPException(503, {'code': 'HOSPITAL_NOT_CONFIGURED', 'message': '병원 검색 설정이 필요합니다.'})

    params = {'query': query, 'x': lng, 'y': lat, 'radius': radius, 'sort': 'distance', 'size': size}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(KAKAO_KEYWORD_URL, headers={'Authorization': f'KakaoAK {key}'}, params=params)
        response.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(504, {'code': 'HOSPITAL_TIMEOUT', 'message': '병원 검색 응답 시간이 초과되었습니다.'}) from None
    except httpx.HTTPStatusError:
        raise HTTPException(503, {'code': 'HOSPITAL_UPSTREAM_ERROR', 'message': '병원 검색 서비스 호출에 실패했습니다.'}) from None
    except httpx.RequestError:
        raise HTTPException(503, {'code': 'HOSPITAL_UNREACHABLE', 'message': '병원 검색 서버에 접속할 수 없습니다.'}) from None

    try:
        items = [
            Hospital(
                name=d['place_name'],
                category=_clean(d.get('category_name')),
                address=_clean(d.get('address_name')),
                road_address=_clean(d.get('road_address_name')),
                phone=_clean(d.get('phone')),
                distance_m=int(d['distance']) if d.get('distance') else None,
                lat=float(d['y']),
                lng=float(d['x']),
                place_url=_clean(d.get('place_url')),
            )
            for d in response.json()['documents']
        ]
    except (ValueError, KeyError, TypeError):
        raise HTTPException(502, {'code': 'HOSPITAL_INVALID_RESPONSE', 'message': '병원 검색 응답 형식이 올바르지 않습니다.'}) from None
    return HospitalList(items=items, total=len(items))
