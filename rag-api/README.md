# MOVAR RAG API

두피 진단 결과를 기반으로 헤어케어 상품을 추천하는 MOVAR의 RAG API 서비스입니다. 6개 두피 증상의 심각도(Level 0~3)와 선택적 사용자 정보를 입력받아, 로컬 상품 데이터에 대해 **Hybrid Retrieval → Qwen2.5 14B 적합도 평가 → Top 3 추천**을 수행합니다.

현재 데모는 비전 모델의 출력값을 웹 화면에서 직접 입력하며, 상품 정보는 로컬 CSV와 사전 생성된 벡터 인덱스를 사용합니다. 팀 저장소 내 `rag-api/`는 별도의 Python 실행 환경을 갖는 독립 서비스 디렉터리입니다.

## 1. 개발 환경 및 실행

### 1.1 요구 환경

- **OS:** Windows / PowerShell 기준
- **Python:** 3.11 권장 (현재 개발·테스트 환경: Python 3.11)
- **LLM:** [Ollama](https://ollama.com/download/windows) + `qwen2.5:14b`
- **Embedding:** `jhgan/ko-sroberta-multitask` (`sentence-transformers`)
- **패키지:** `requirements.txt` 참조

Qwen2.5 14B는 약 9GB의 모델 다운로드가 필요하며, GPU가 없는 환경에서도 CPU 추론은 가능하지만 속도가 느릴 수 있습니다. **Ollama 및 모델 파일은 Python 가상환경에 설치되지 않고 운영체제의 Ollama 저장소에서 관리**됩니다. 임베딩 모델도 처음 실행 시 Hugging Face에서 다운로드될 수 있으므로 최초 구동에는 인터넷 연결이 필요합니다.

### 1.2 Python 가상환경

모든 명령은 **`MOVAR/rag-api`에서 실행**합니다. 저장소 루트(`MOVAR`)에서 터미널을 열었다면 먼저 이동합니다.

```powershell
cd .\rag-api
```

가상환경은 서비스 폴더 바로 아래인 **`rag-api/.venv/`**에 생성합니다. 다른 팀원 프로젝트의 가상환경과 공유하지 않습니다.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

PowerShell에서 스크립트 실행 정책으로 활성화가 차단된다면, 현재 세션에 한해 실행을 허용한 뒤 다시 활성화합니다.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

인터프리터 확인:

```powershell
python -c "import sys; print(sys.executable)"
```

출력 경로가 `...\MOVAR\rag-api\.venv\Scripts\python.exe`이면 정상입니다. VS Code에서도 동일한 인터프리터를 선택합니다. 터미널에 Conda `(base)`가 표시된다면 필요에 따라 `conda deactivate` 후 `.venv`를 활성화하면 됩니다.

### 1.3 Ollama 및 Qwen2.5 14B

1. [Ollama Windows](https://ollama.com/download/windows) 설치
2. 새 PowerShell 터미널에서 Ollama와 모델 설치 확인

```powershell
ollama --version
ollama pull qwen2.5:14b
ollama list
```

Ollama가 백그라운드에서 실행 중이면 별도의 `ollama serve` 명령은 필요하지 않습니다. 서버가 실행 중인지 확인하려면 다음 API를 조회합니다.

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

Ollama 서버가 실행되지 않는 경우 **별도 터미널**에서 `ollama serve`를 실행합니다. 이미 실행 중이라면 포트 점유 오류가 날 수 있으므로 중복 실행하지 않습니다.

Qwen의 로컬 추론을 직접 확인하려면:

```powershell
ollama run qwen2.5:14b
```

`ollama list`에 모델이 있더라도 API가 실행되는지, 실제 응답이 가능한지는 별도 확인해야 합니다. 이전에 Ollama에 설치한 동일 모델이 있다면 다시 설치할 필요는 없습니다.

### 1.4 FastAPI 실행

`rag-api/`에서 가상환경 활성화 후:

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

| 주소 | 용도 |
| --- | --- |
| `http://127.0.0.1:8000/` | 데모 웹 화면 |
| `http://127.0.0.1:8000/docs` | Swagger UI / API 요청 테스트 |
| `http://127.0.0.1:8000/health` | FastAPI 프로세스 상태 확인 |

> `/health`의 `running` 응답은 **FastAPI가 실행 중임을 의미**합니다. Ollama 설치 여부나 Qwen 추론 성공을 검증하지는 않습니다. 실제 모델 호출 검증은 증상 중 하나 이상을 Level 1~3으로 설정한 뒤 추천을 실행해야 합니다.

### 1.5 테스트

테스트 전용 의존성은 기본 `requirements.txt`에 포함되어 있지 않을 수 있습니다.

```powershell
python -m pip install pytest httpx
python -m pytest tests -v
```

테스트에서는 가짜 Embedding 및 가짜 LLM을 사용하여 후보 수, 카테고리 필터, API 응답 등을 검증합니다. **테스트 통과가 실제 Qwen 응답 또는 추천 품질을 보장하지는 않습니다.** 실제 추론은 1.3~1.4의 Ollama 환경에서 별도로 확인합니다.

### 1.6 선택 환경변수

기본 설정으로 실행할 경우 별도 설정이 필요하지 않습니다. 변경이 필요한 경우 **FastAPI를 시작하는 PowerShell 세션**에 환경변수를 지정합니다.

```powershell
$env:OLLAMA_HOST = "http://localhost:11434"
$env:MOVAR_LLM_MODEL = "qwen2.5:14b"
$env:MOVAR_LLM_TIMEOUT = "300"
```

| 환경변수 | 기본값 | 역할 |
| --- | --- | --- |
| `OLLAMA_HOST` | `http://localhost:11434` | API에서 연결할 Ollama 주소 |
| `MOVAR_LLM_MODEL` | `qwen2.5:14b` | 추론 모델 이름 |
| `MOVAR_LLM_TIMEOUT` | `300` | Ollama 요청 제한시간(초) |
| `MOVAR_HYBRID_EMBEDDING_K` | `7` | Embedding 기반 후보 수 |
| `MOVAR_HYBRID_INGREDIENT_K` | `15` | 성분 기반 후보 수 |
| `MOVAR_HYBRID_TOTAL_K` | `22` | 총 후보 수 상한 |
| `MOVAR_PRODUCTS_CSV` | `data/products.csv` | 상품 CSV 경로 |
| `MOVAR_INDEX_DIR` | `data/index` | 벡터 인덱스 경로 |
| `MOVAR_EMBED_MODEL` | `jhgan/ko-sroberta-multitask` | 임베딩 모델 이름 또는 로컬 경로 |
| `MOVAR_DEMO_KEY` | 미설정 | 데모 API 요청용 선택 인증키 |

**주의:** 현재 구현은 환경변수를 `os.getenv()`로 직접 읽으며, **`.env` 파일을 자동 로드하지 않습니다.** `.env.example`은 참고용입니다. 설정을 바꿨다면 FastAPI 프로세스를 재시작합니다.

`MOVAR_DEMO_KEY`를 지정한 경우 `/recommend`, `/jobs` API 호출에 `X-Movar-Demo-Key` 헤더가 필요합니다. 웹의 **시연 접근키** 입력란은 이 값을 전송하기 위한 필드이며, 키를 설정하지 않았다면 비워 둡니다. 원격 서버의 Ollama 11434 포트를 공개 인터넷에 직접 노출하지 마세요.

## 2. 프로젝트 구조

```text
rag-api/
├── app/
│   ├── main.py                         # FastAPI 엔드포인트 및 비동기 작업 처리
│   ├── config.py                       # 데이터 경로, 증상·카테고리, 검색·모델 설정
│   ├── schemas/
│   │   ├── request.py                  # 입력값 검증 (증상, 프로필, 카테고리)
│   │   └── response.py                 # 응답 스키마 확장용 파일 (현재 dict JSON 사용)
│   ├── services/
│   │   └── recommendation_service.py   # Retrieval → LLM 평가 → Top3 추천 연결
│   ├── llm/
│   │   ├── qwen_client.py              # Ollama 통신 및 점수 JSON 검증
│   │   ├── test5_prompt.py             # Local LLM Test 5 프롬프트
│   │   └── evidence.py                 # 성분 근거 기반 설명 데이터 구성
│   └── retrieval/
│       ├── retriever.py                # Hybrid Retrieval 및 카테고리·가격 필터
│       ├── query_builder.py            # 두피 증상 → 검색용 쿼리 생성
│       ├── build_index.py              # CSV 기반 상품 벡터 인덱스 재생성
│       ├── embedding/
│       │   ├── embedding_model.py      # 한국어 Embedding 모델 / 테스트 대체 모델
│       │   └── vector_store.py         # 벡터 저장·로드 및 코사인 유사도 검색
│       └── preprocessing/
│           ├── ingredient_normalizer.py # 전성분 명칭 정규화
│           ├── ingredient_scores.py     # 증상별 성분 적합도 점수·근거 계산
│           ├── product_document.py      # 검색 대상 상품 Document 구성
│           └── gentleness.py            # 증상 전체 0일 때 저자극 기준 계산
├── data/
│   ├── products.csv                    # 로컬 상품 원본 데이터
│   └── index/
│       ├── vectors.npy                 # 정규화된 상품 임베딩 벡터
│       ├── records.json                # 검색용 상품 레코드·메타데이터
│       └── meta.json                   # 인덱스 모델·차원·상품 개수 정보
├── frontend/
│   └── index.html                      # 증상·카테고리 입력 및 상품 결과 UI
├── tests/
│   └── test_demo_pipeline.py           # API·Retrieval 오프라인 테스트
├── requirements.txt                    # Python 실행 의존성
├── .env.example                        # 환경변수 예시 (자동 로드 아님)
├── .gitignore                          # 가상환경·캐시·비밀 설정 제외
└── README.md
```

각 `__init__.py`는 Python 패키지 경로를 구성하는 파일입니다. 이전 실험에서 사용한 `allergen_mapper.py`가 남아 있더라도 **현재 추천 파이프라인에는 연결되지 않으며**, 알레르기 필터링 기능이 구현된 것으로 간주하지 않습니다.

## 3. RAG 추천 처리 구조

```text
수동 두피 진단값 (6종 × Level 0~3)
          + 사용자 프로필(선택)
          + 상품 카테고리(복수 선택)
                    │
                    ▼
           Query Builder (규칙 기반)
                    │
                    ▼
      카테고리 / 최대 가격 하드 필터
                    │
                    ▼
          Hybrid Retrieval
          ├─ Embedding 유사도 Top 7
          └─ 성분 적합도 Top 15 (중복 제외)
                    │
                    ▼
           최대 22개 후보 상품
                    │
                    ▼
      Qwen2.5:14b (Test 5 프롬프트)
      후보별 적합도 점수 0~100 반환
                    │
                    ▼
      Python 점수 내림차순 정렬
      (동점: 기존 후보 입력 순서)
                    │
                    ▼
      최종 Top 3 + 상품 정보/성분 근거
                    │
                    ▼
           FastAPI JSON → HTML
```

### 검색 단계

- 검색 Query는 증상 심각도를 바탕으로 **규칙 기반**으로 생성하며, 별도의 LLM을 호출하지 않습니다.
- Embedding 모델은 `jhgan/ko-sroberta-multitask`입니다. 저장된 벡터는 L2 정규화되어 있으며 벡터 내적을 이용해 코사인 유사도를 계산합니다.
- 성분 검색은 증상별 성분 점수에 해당 증상의 Level을 반영해 후보를 선정합니다. 두 검색 결과에서 중복 상품은 제거합니다.
- **7+15=22개는 상한/목표 구성**입니다. 선택 카테고리, 가격 조건, 상품 수 또는 성분 적합 후보 부족에 따라 실제 수가 줄거나 검색 후보로 보충될 수 있습니다. 선택하지 않은 카테고리의 상품을 임의로 추가하지 않습니다.
- 사용자 정보 중 **최대 가격은 검색 단계의 필터**이며, 연령대·머리 감는 주기는 Qwen 평가 시 보조 정보로 전달합니다.

### LLM 평가 및 추천 단계

- `qwen2.5:14b`에 **Local LLM Test 5 프롬프트**, `temperature=0`, JSON Schema 제약을 적용합니다.
- Qwen은 후보별 `C01`, `C02` 등의 식별키에 대해 **점수만 반환**합니다. 모델이 최종 상품 순위를 작성하지 않습니다.
- Python이 점수를 검증하고 내림차순 정렬하여 Top 3를 선정합니다. 반환 점수는 상품 적합도 판단을 위한 **내부 상대 점수이며 확률이 아닙니다.**
- 추천 이유(`reason`)는 현재 **Python에서 상품 성분 근거를 이용해 구성**합니다. Qwen이 자연어 추천 이유를 생성하는 구조가 아닙니다.
- 6개 증상이 **모두 Level 0**이면 Qwen 호출 없이 저자극 기준으로 상품을 선정합니다.

## 4. API 사용

| Method | Endpoint | 설명 |
| --- | --- | --- |
| `GET` | `/` | HTML 데모 화면 |
| `GET` | `/health` | API 프로세스 상태 |
| `POST` | `/recommend` | 동기 추천 처리 (Swagger 테스트용) |
| `POST` | `/jobs` | 추천 작업 등록, `job_id` 반환 |
| `GET` | `/jobs/{job_id}` | 작업 상태 조회 (`queued`, `running`, `done`, `error`) |

웹 프론트엔드는 `/jobs`를 호출한 후 상태를 폴링합니다. 실제 추론 중 응답 시간이 길어질 수 있어 작업 요청/조회 방식을 사용합니다.

요청 예시 (`POST /recommend` 또는 `POST /jobs`):

```json
{
  "symptoms": {
    "micro_keratin": 0,
    "excess_sebum": 1,
    "follicular_erythema": 0,
    "follicular_pustule": 0,
    "dandruff": 2,
    "hair_loss": 3
  },
  "user_info": {
    "age_group": "20대",
    "wash_frequency": "하루 1회",
    "max_price": 30000
  },
  "categories": ["shampoo", "tonic"]
}
```

`categories`는 `shampoo`, `scaler`, `treatment`, `tonic` 중 하나 이상을 선택합니다. UI에서는 필수지만 API에서 생략하면 기존 호환성을 위해 전체 카테고리를 검색합니다. 선택한 여러 카테고리에서 **총 Top 3를 선정**하며, 각 카테고리에서 3개씩 반환하는 방식은 아닙니다. `user_info`는 선택사항입니다.

## 5. 상품 데이터 및 인덱스 관리

최초 실행에는 저장소의 `data/products.csv`와 `data/index/`를 그대로 사용합니다. **정상적으로 인덱스 파일이 있는 경우 최초 실행 시 다시 생성할 필요는 없습니다.**

상품 데이터가 추가·수정되어 검색 문서/벡터가 바뀌었다면 다음 명령으로 인덱스를 재생성합니다.

```powershell
python -m app.retrieval.build_index
```

`vectors.npy`, `records.json`, `meta.json`은 한 세트로 관리합니다. 실행 시 Embedding 모델 설정과 `meta.json`의 모델 이름이 일치해야 하며, 다른 모델을 사용하려면 해당 모델로 인덱스를 재생성해야 합니다. 테스트용 `hashing` 백엔드는 실제 추천 품질 평가에 사용하지 않습니다.

`.venv/`, `__pycache__/`, `.env`는 Git에서 제외합니다. 반면 서비스 재현에 필요한 `requirements.txt`, 상품 CSV 및 인덱스 파일은 팀에서 동일한 버전을 사용하는 것이 좋습니다.

## 6. 문제 해결

| 현상 | 확인할 사항 |
| --- | --- |
| `Activate.ps1`을 찾을 수 없음 | 현재 위치가 `MOVAR/rag-api`인지 확인 (`pwd`). `.venv`가 이 폴더 안에 있어야 함 |
| `source` 명령이 동작하지 않음 | PowerShell에서는 `source` 대신 `.\.venv\Scripts\Activate.ps1` 사용 |
| `No module named ...` | `.venv` 인터프리터 선택 및 `python -m pip install -r requirements.txt` 확인 |
| 서버는 열리는데 추천 실행 시 Ollama 오류 | `ollama list`, `/api/tags`, `qwen2.5:14b` 설치 및 서버 실행 상태 확인 |
| 첫 추천 요청이 오래 걸림 | 최초 Embedding 모델 다운로드·로드 또는 Qwen 모델 로딩 가능성 확인 |
| Embedding 모델/인덱스 불일치 | `data/index/meta.json`의 `model`과 `MOVAR_EMBED_MODEL` 일치 여부 확인 |
| 후보가 22개 미만 | 선택 카테고리·가격 제한 및 유효 상품 수 확인 (정상 동작 가능) |
| `401` 응답 | `MOVAR_DEMO_KEY` 설정 및 `X-Movar-Demo-Key` 값 확인 |
| API 테스트에서 `pytest`/`httpx` 오류 | `python -m pip install pytest httpx` 실행 |

## 7. 현재 범위 및 후속 작업

**구현 범위:** 수동 두피 진단값 입력, 카테고리·가격 필터, 로컬 CSV 기반 Hybrid RAG, Qwen 상품 점수 평가, FastAPI, 상품 Top 3 웹 표시.

**추후 연동:** 비전 모델 자동 입력, Supabase 상품 DB, 별도 LLM 진단 리포트, 알레르기 분석·LoRA 개선, 클라우드 배포. 현재 저장소의 데모 코드만으로 해당 기능이 완성된 것은 아닙니다.
