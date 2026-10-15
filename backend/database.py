"""Server-side Supabase Data API access. Credentials never leave this module."""
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException


async def read_products(limit: int = 1) -> tuple[list, int]:
    load_dotenv(Path(__file__).with_name('.env'))
    url = os.getenv('SUPABASE_URL', '').rstrip('/')
    key = os.getenv('SUPABASE_KEY', '')
    if not url or not key:
        raise HTTPException(503, {'code': 'DB_NOT_CONFIGURED', 'message': 'DB 연결 설정이 필요합니다.'})
    headers = {'apikey': key, 'Prefer': 'count=exact'}
    if key.startswith('eyJ'):
        headers['Authorization'] = f'Bearer {key}'
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f'{url}/rest/v1/products', headers=headers,
                params={'select': 'product_id,product_name,brand_name', 'order': 'product_id.asc', 'limit': limit},
            )
        response.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(504, {'code': 'DB_TIMEOUT', 'message': 'DB 응답 시간이 초과되었습니다.'}) from None
    except httpx.HTTPStatusError as exc:
        try:
            code = exc.response.json().get('code')
        except (ValueError, AttributeError):
            code = None
        code = 'PGRST002' if code == 'PGRST002' else 'DB_UPSTREAM_ERROR'
        raise HTTPException(503, {'code': code, 'message': 'Supabase Data API 연결에 실패했습니다.'}) from None
    except httpx.RequestError:
        raise HTTPException(503, {'code': 'DB_UNREACHABLE', 'message': 'DB 서버에 접속할 수 없습니다.'}) from None
    try:
        rows = response.json()
        total = int(response.headers['content-range'].rsplit('/', 1)[1])
        if not isinstance(rows, list):
            raise ValueError('Unexpected response')
    except (ValueError, KeyError):
        raise HTTPException(502, {'code': 'DB_INVALID_RESPONSE', 'message': 'DB 응답 형식이 올바르지 않습니다.'}) from None
    return rows, total
