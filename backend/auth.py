"""Supabase Auth JWT verification. The token is checked by Supabase's own Auth server."""
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(code: str, message: str) -> HTTPException:
    return HTTPException(401, {'code': code, 'message': message}, headers={'WWW-Authenticate': 'Bearer'})


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """Return the Supabase user ({'id', 'email'}) for the Bearer access token, or raise 401."""
    if credentials is None:
        raise _unauthorized('AUTH_REQUIRED', '로그인이 필요합니다.')

    load_dotenv(Path(__file__).with_name('.env'))
    url = os.getenv('SUPABASE_URL', '').rstrip('/')
    key = os.getenv('SUPABASE_KEY', '')
    if not url or not key:
        raise HTTPException(503, {'code': 'AUTH_NOT_CONFIGURED', 'message': '인증 설정이 필요합니다.'})

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f'{url}/auth/v1/user',
                headers={'apikey': key, 'Authorization': f'Bearer {credentials.credentials}'},
            )
    except httpx.TimeoutException:
        raise HTTPException(504, {'code': 'AUTH_TIMEOUT', 'message': '인증 서버 응답 시간이 초과되었습니다.'}) from None
    except httpx.RequestError:
        raise HTTPException(503, {'code': 'AUTH_UNREACHABLE', 'message': '인증 서버에 접속할 수 없습니다.'}) from None

    if response.status_code in (400, 401, 403):
        raise _unauthorized('AUTH_INVALID_TOKEN', '인증 정보가 만료되었거나 유효하지 않습니다.')
    if response.status_code != 200:
        raise HTTPException(503, {'code': 'AUTH_UPSTREAM_ERROR', 'message': '인증 서버 확인에 실패했습니다.'})

    try:
        user = response.json()
        return {'id': user['id'], 'email': user.get('email')}
    except (ValueError, KeyError, AttributeError):
        raise HTTPException(502, {'code': 'AUTH_INVALID_RESPONSE', 'message': '인증 서버 응답 형식이 올바르지 않습니다.'}) from None
