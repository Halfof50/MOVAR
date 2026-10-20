# MOVAR 백엔드

Python + FastAPI + Uvicorn으로 구성한 개발 환경입니다.
서버 상태 확인, Supabase 연결 확인, 제품 목록 조회, 로그인 토큰 검증, 두피 사진 분석(이미지 모델 서버 연동),
제품 추천(추천 모델 서버 연동), LLM 리포트 생성, 주변 병원 검색 API를 제공합니다.
사용자 데이터 저장(문진·분석·리포트), 엔드포인트별 로그인 검사, 배포는 아직 구현하지 않았습니다.
`mock_ai.py`는 `POST /reports/mock`의 흐름 확인용 가짜 값입니다.

## 최초 설치 (Windows PowerShell / Python 3.12)

VS Code에서 터미널을 열고 실행합니다. [uv](https://docs.astral.sh/uv/)가 필요합니다.

```powershell
cd <저장소 경로>\backend
uv venv
uv pip install -r requirements.txt
```

다른 경로에 저장소를 받았다면 해당 저장소의 `backend` 폴더로 이동하세요.
가상환경을 활성화하지 않고 전용 Python을 직접 사용하므로 PowerShell 실행 정책을 변경할 필요가 없습니다.
`.venv`는 만든 위치의 절대 경로가 들어가므로 폴더를 옮기거나 이름을 바꾸면 지우고 다시 만들어야 합니다.

`requirements.txt` 하나에 함께 검증한 전체 패키지의 정확한 버전이 들어 있습니다.
위쪽은 코드가 직접 쓰는 패키지, 아래쪽은 그 패키지가 함께 설치하는 패키지입니다.
버전을 올리거나 패키지를 추가·삭제할 때는 이 파일을 고친 뒤 설치하고 서버가 정상 동작하는지 확인하세요.

## 서버 실행

`backend` 폴더에서 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

- API 문서·테스트: http://127.0.0.1:8000/docs
- 상태 확인: http://127.0.0.1:8000/health
- API 명세 JSON: http://127.0.0.1:8000/openapi.json
- 종료: 실행 중인 터미널에서 `Ctrl+C`

`--reload`는 코드 변경 시 개발 서버를 다시 불러옵니다.
이 설정은 본인 컴퓨터에서 접속하는 개발용 서버입니다.
8000 포트를 이미 사용 중이면 기존 서버를 종료하거나 `--port 8001`로 실행하세요.

## 확인 방법

`/docs`에서 `GET /health` → `Try it out` → `Execute`를 누르면
HTTP 200과 다음 응답이 나옵니다.

```json
{"status":"ok","service":"movar-backend","version":"0.1.0"}
```

`status: ok`는 이 백엔드 서버가 실행 중이라는 뜻이며, DB 연결 성공을 의미하지 않습니다.

공식 실행 안내: https://fastapi.tiangolo.com/deployment/manually/

## Supabase DB 연결

`backend/.env.example`을 `backend/.env`로 복사하고 `SUPABASE_KEY`에
서버용 키를 설정합니다. 현재 개발 PC에는 로컬 `.env`를 설정해 두었습니다.
실제 키 파일은 Git에서 제외되며 프론트엔드에 전달하지 않습니다.
`.env` 변경 후 서버를 재시작하세요.

- `GET /health`: 서버 실행 상태만 확인
- `GET /health/db`: 제품 테이블을 실제 조회한 뒤 성공 시 연결 상태와 제품 수 반환
- `GET /products?limit=10`: 제품 ID, 이름, 브랜드와 전체 제품 수 반환

이 API는 제품 테이블을 읽기만 하며 테이블 생성이나 데이터 변경을 하지 않습니다.
서버용 키를 사용하는 로컬 개발용 구성입니다. 사용자 데이터 API를 추가할 때는
인증·사용자별 접근 검증이 별도로 필요합니다.

### 연결 검증 결과

프로젝트 관리자가 Data API를 활성화한 뒤 실제 서버에서 다음을 확인했습니다.

- `/health`: HTTP 200, 서버 정상
- `/health/db`: HTTP 200, `database: connected`, 제품 241건
- `/products?limit=2`: HTTP 200, 실제 제품 2건 및 전체 제품 수 241 반환

앞서 발생했던 HTTP 503 / `PGRST002`는 활성화 후 해소되었습니다.
DB 테이블과 데이터는 수정하지 않았습니다. 제품 수는 검증 시점 기준이며,
2026-10-16 재확인 시에는 145건이었습니다.

## 외부 서비스 키

`.env`에 다음 키가 더 필요합니다. 모두 backend에서만 사용하며 프론트로 전달하지 않습니다.

- `GEMINI_API_KEY`: LLM 리포트 생성(`POST /reports`, `POST /reports/mock`). 모델은 `GEMINI_MODEL`로 바꿀 수 있습니다.
- `KAKAO_REST_API_KEY`: 주변 병원 검색(`GET /hospitals`).
- `MOVAR_API_BASE_URL`: 추천 모델 서버(RunPod) 주소(`POST /recommendations`).
- `MOVAR_VISION_API_BASE_URL`: 이미지 모델 서버(`ai/inference`) 주소(`POST /scalp-analyses`). backend와 포트가 겹치지 않게 다른 포트(예: 8001)로 실행합니다.

로그인 토큰 검증(`GET /me`)은 위의 `SUPABASE_KEY`를 그대로 사용합니다.
엔드포인트별 요청·응답은 `API_SPEC.md`를 참고하세요.

공식 오류 안내:
https://supabase.com/docs/guides/troubleshooting/postgrest-error-pgrst002-could-not-query-the-database-for-the-schema-cache-c396e9
