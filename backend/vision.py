"""Scalp image analysis via the team's vision model server (ai/inference): photo in, six symptom levels out."""
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException
from pydantic import BaseModel, ValidationError

from recommend import Symptoms

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # same limit as the vision server
# The vision server returns its six heads as value_1..value_6 in this order.
HEAD_TO_SYMPTOM = {
    'value_1': 'micro_keratin',
    'value_2': 'excess_sebum',
    'value_3': 'follicular_erythema',
    'value_4': 'follicular_pustule',
    'value_5': 'dandruff',
    'value_6': 'hair_loss',
}


class AnalysisResponse(BaseModel):
    symptoms: Symptoms
    model: str | None


def _image_type(content: bytes) -> str | None:
    if content.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if content.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if content[:4] == b'RIFF' and content[8:12] == b'WEBP':
        return 'image/webp'
    return None


def validate_image(content: bytes) -> str:
    """Return the real content type of the upload, or raise 400/413/415."""
    if not content:
        raise HTTPException(400, {'code': 'IMAGE_EMPTY', 'message': '비어 있는 파일입니다.'})
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, {'code': 'IMAGE_TOO_LARGE', 'message': '이미지는 10MB 이하만 허용됩니다.'})
    content_type = _image_type(content)
    if content_type is None:
        raise HTTPException(415, {'code': 'IMAGE_UNSUPPORTED', 'message': 'JPEG, PNG, WEBP 이미지만 지원합니다.'})
    return content_type


async def analyze_image(content: bytes) -> AnalysisResponse:
    content_type = validate_image(content)

    load_dotenv(Path(__file__).with_name('.env'))
    base_url = os.getenv('MOVAR_VISION_API_BASE_URL', '').rstrip('/')
    if not base_url:
        raise HTTPException(503, {'code': 'VISION_NOT_CONFIGURED', 'message': '이미지 분석 서버 설정이 필요합니다.'})

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(f'{base_url}/predict', files={'file': ('scalp', content, content_type)})
        response.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(504, {'code': 'VISION_TIMEOUT', 'message': '이미지 분석 응답 시간이 초과되었습니다.'}) from None
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 413, 415):
            raise HTTPException(422, {'code': 'IMAGE_REJECTED', 'message': '분석할 수 없는 이미지입니다. 다른 사진으로 시도해 주세요.'}) from None
        raise HTTPException(503, {'code': 'VISION_UPSTREAM_ERROR', 'message': '이미지 분석 서버 호출에 실패했습니다.'}) from None
    except httpx.RequestError:
        raise HTTPException(503, {'code': 'VISION_UNREACHABLE', 'message': '이미지 분석 서버에 접속할 수 없습니다.'}) from None

    try:
        body = response.json()
        levels = {HEAD_TO_SYMPTOM[item['key']]: item['grade'] for item in body['symptoms']}
        return AnalysisResponse(symptoms=Symptoms(**levels), model=body.get('model'))
    except (ValueError, KeyError, TypeError, AttributeError, ValidationError):
        raise HTTPException(502, {'code': 'VISION_INVALID_RESPONSE', 'message': '이미지 분석 응답 형식이 올바르지 않습니다.'}) from None
