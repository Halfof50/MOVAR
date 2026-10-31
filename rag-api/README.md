# MOVAR RAG API

두피 상태 기반 헤어케어 상품 추천 API. 비전 모델 연동 전 단계에서는 6개 두피 증상(Level 0~3)을 수동 입력한다. 로컬 상품 CSV 및 벡터 인덱스를 사용하며, Hybrid Retrieval로 선정한 후보를 Qwen2.5 14B로 평가한 후 상위 3개 상품을 반환한다.

## 1. 실행 환경 구성

### 1.1. 요구 환경

| 항목 | 구성 |
| --- | --- |
| OS | Windows / PowerShell 기준 |
| Python | 3.11 |
| Python 의존성 | `requirements.txt` |
| LLM 런타임 | Ollama |
| LLM 모델 | `qwen2.5:14b` |
| Embedding 모델 | `jhgan/ko-sroberta-multitask` |
| 상품 데이터 | `data/products.csv` 및 `data/index/` |

- 실행 기준 디렉터리: `MOVAR/rag-api/`
- Python 가상환경: `rag-api/.venv/`
- Ollama 및 Qwen 모델: Python 가상환경과 별도로 설치·관리
- 최초 Embedding 모델 로드 시 Hugging Face 모델 다운로드가 발생할 수 있음

### 1.2. Python 가상환경 및 패키지 설치

팀 저장소의 `MOVAR/` 디렉터리에서 실행:

```powershell
cd .\rag-api
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

PowerShell 실행 정책으로 활성화가 차단된 경우(현재 세션만 적용):

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

가상환경 확인:

```powershell
python -c "import sys; print(sys.executable)"
```

정상 경로: `...\MOVAR\rag-api\.venv\Scripts\python.exe`

VS Code 인터프리터도 동일한 `.venv\Scripts\python.exe`로 지정한다.

### 1.3. Ollama 및 Qwen 설치

Ollama Windows 설치: <https://ollama.com/download/windows>

```powershell
ollama --version
ollama pull qwen2.5:14b
ollama list
```

Ollama API 확인:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

- 기본 API 주소: `http://127.0.0.1:11434`
- Ollama 서버가 중지된 경우 별도 터미널에서 `ollama serve` 실행
- Ollama가 이미 백그라운드에서 실행 중이면 `ollama serve` 중복 실행 불필요
- 모델 실행 확인(선택): `ollama run qwen2.5:14b`
- `ollama list`에 모델이 이미 존재하면 재다운로드 불필요

### 1.4. API 서버 실행 및 검증

`MOVAR/rag-api/`에서 가상환경 활성화 후 실행:

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

- 데모 UI: <http://127.0.0.1:8000/>
- API 테스트 UI: <http://127.0.0.1:8000/docs>

자동 테스트:

```powershell
python -m pip install pytest httpx
python -m pytest tests -v
```

자동 테스트는 후보 검색 및 API 처리 로직에 대한 오프라인 검증이다. 실제 Qwen 추론은 Ollama 실행 상태에서 증상값 중 하나 이상을 Level 1~3으로 설정하여 확인한다.

실행 설정 변경이 필요한 경우 FastAPI 시작 전에 PowerShell 환경변수를 지정한다.

```powershell
$env:OLLAMA_HOST = "http://localhost:11434"
$env:MOVAR_LLM_MODEL = "qwen2.5:14b"
$env:MOVAR_LLM_TIMEOUT = "300"
```

환경변수를 지정하지 않으면 위 기본값을 사용한다. 현재 코드는 `.env` 파일을 자동 로드하지 않는다.

## 2. 프로젝트 구조

```text
rag-api/
├── app/
│   ├── main.py                         # FastAPI 서버, 추천 요청 및 작업 처리
│   ├── config.py                       # 데이터 경로, 모델, 검색 설정
│   ├── schemas/
│   │   ├── request.py                  # 요청 JSON 및 입력값 검증
│   │   └── response.py                 # 응답 스키마 확장용 모듈
│   ├── services/
│   │   └── recommendation_service.py   # 검색·LLM 평가·최종 추천 통합
│   ├── llm/
│   │   ├── qwen_client.py              # Ollama 호출 및 점수 응답 검증
│   │   ├── test5_prompt.py             # 검증된 Local LLM Test 5 프롬프트
│   │   └── evidence.py                 # 상품 성분 근거 데이터 구성
│   └── retrieval/
│       ├── retriever.py                # Hybrid 검색 및 필터링
│       ├── query_builder.py            # 증상 기반 검색 쿼리 생성
│       ├── build_index.py              # 상품 임베딩 인덱스 생성
│       ├── embedding/
│       │   ├── embedding_model.py      # 한국어 임베딩 모델
│       │   └── vector_store.py         # 벡터 로드 및 유사도 계산
│       └── preprocessing/
│           ├── ingredient_normalizer.py # 성분명 표준화
│           ├── ingredient_scores.py     # 증상별 성분 적합도 계산
│           ├── product_document.py      # 상품 검색 Document 생성
│           └── gentleness.py            # 모든 증상 0인 경우의 저자극 평가
├── data/
│   ├── products.csv                    # 상품 데이터
│   └── index/
│       ├── vectors.npy                 # 상품 임베딩 벡터
│       ├── records.json                # 벡터 대응 상품 레코드
│       └── meta.json                   # 인덱스 메타데이터
├── frontend/
│   └── index.html                      # 데모 입력 및 추천 결과 표시
├── tests/
│   └── test_demo_pipeline.py           # 추천 파이프라인·API 테스트
├── requirements.txt                    # Python 의존성
├── .gitignore                          # 가상환경·캐시·환경변수 제외
└── README.md
```

각 디렉터리의 `__init__.py`는 Python 패키지 인식용 파일이다.

## 3. RAG 추천 구조

```text
두피 증상 6종(Level 0~3)
+ 사용자 정보(연령대 / 머리 감는 주기 / 최대 가격)
+ 선택 카테고리
        │
        ▼
검색 쿼리 생성 및 카테고리·가격 필터
        │
        ▼
Hybrid Retrieval
├─ Embedding 유사도: 7개
└─ 성분 적합도: 15개 (기선정 후보 중복 제외)
        │
        ▼
후보 상품 최대 22개
        │
        ▼
Qwen2.5 14B / Test 5 프롬프트
후보별 적합도 점수(0~100) 반환
        │
        ▼
Python 점수 내림차순 정렬
        │
        ▼
Top 3 + 상품 정보 + 성분 근거
        │
        ▼
FastAPI JSON 응답 / 프론트엔드 출력
```

- Retrieval: `jhgan/ko-sroberta-multitask` 임베딩과 규칙 기반 성분 점수 결합. 상품 중복 제거.
- 후보 수: 기본 7+15, 최대 22개. 선택 카테고리·가격 및 검색 가능 상품 수에 따라 감소 가능.
- 카테고리: `shampoo`, `scaler`, `treatment`, `tonic`. 복수 선택 시 선택된 카테고리 전체에서 Top 3 선정.
- 사용자 정보: 최대 가격은 검색 필터에 사용. 연령대·머리 감는 주기는 LLM 평가 보조 정보로 전달.
- LLM: 상품별 적합도 점수만 JSON으로 반환. 추천 순위는 Python에서 결정.
- 점수: 내부 순위 산정값. 확률값이 아님.
- 추천 이유: 현재 성분 근거 기반 규칙형 문장으로 구성.
- 예외 처리: 6개 증상이 모두 Level 0인 경우 Qwen 호출 없이 저자극 기준으로 추천.

## 4. API 사용 및 입출력 형식

### 4.1. 요청

추천 요청: `POST /recommend` (`Content-Type: application/json`)

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

| 필드 | 형식 | 설명 |
| --- | --- | --- |
| `symptoms` | object | 6개 증상. 각 값 정수 `0~3` |
| `user_info` | object | 선택 입력. 연령대·세척 주기·최대 가격 |
| `categories` | string[] | 선택 카테고리. 미지정 시 전체 상품 검색 |

카테고리는 `shampoo`, `scaler`, `treatment`, `tonic` 중 선택한다. `max_price` 지정 시 1원 이상의 정수를 사용한다. 사용자 정보 미입력 시 `user_info`를 생략할 수 있다.

PowerShell 호출 예시:

```powershell
$body = @{
    symptoms = @{
        micro_keratin = 0
        excess_sebum = 1
        follicular_erythema = 0
        follicular_pustule = 0
        dandruff = 2
        hair_loss = 3
    }
    user_info = @{
        age_group = "20대"
        wash_frequency = "하루 1회"
        max_price = 30000
    }
    categories = @("shampoo", "tonic")
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post `
    -Uri "http://127.0.0.1:8000/recommend" `
    -ContentType "application/json" `
    -Body $body
```

### 4.2. 응답

`/recommend`는 추천 결과를 JSON으로 반환한다. 아래는 주요 필드만 나타낸 예시이며, 상품 정보와 수치는 형식 설명용이다.

```json
{
  "status": "ok",
  "candidate_count": 22,
  "categories": ["shampoo", "tonic"],
  "recommendations": [
    {
      "rank": 1,
      "product_id": 1,
      "product_name": "예시 상품",
      "category": "shampoo",
      "category_kr": "샴푸",
      "price": 18000,
      "rating": 4.8,
      "reviews": 1000,
      "image": "https://example.com/image.jpg",
      "link": "https://example.com/product",
      "llm_score": 94,
      "matched_symptoms": ["hair_loss"],
      "reason": "증상 및 성분 근거 기반 추천 설명"
    }
  ],
  "llm_calls": 1,
  "timing_ms": {
    "total_ms": 19000
  }
}
```

- `recommendations`: 적합도 기준 상위 상품 배열. 정상적으로 후보가 3개 이상인 경우 최대 3개 반환.
- `llm_score`: Qwen 평가 점수. 응답에 포함되지만 프론트엔드에서 표시 여부를 제어할 수 있음.
- `reason`: 성분 근거를 조합한 추천 문장.
- `status`: `ok` / `empty` 등 처리 결과. 필터 조건에 맞는 상품이 없으면 빈 추천 배열 반환.
- 모든 증상 Level 0인 경우 LLM을 호출하지 않으므로 `llm_score`는 `null`, `llm_calls`는 `0`.

### 4.3. 비동기 호출(웹 데모)

긴 추론 요청은 다음과 같이 등록 후 결과를 조회한다.

```powershell
$job = Invoke-RestMethod -Method Post `
    -Uri "http://127.0.0.1:8000/jobs" `
    -ContentType "application/json" `
    -Body $body

$job.job_id
Invoke-RestMethod "http://127.0.0.1:8000/jobs/$($job.job_id)"
```

작업 등록 응답:

```json
{
  "job_id": "작업-식별자",
  "state": "queued"
}
```

작업 완료 응답:

```json
{
  "state": "done",
  "result": {
    "status": "ok",
    "candidate_count": 22,
    "recommendations": []
  }
}
```

`result`에는 4.2절의 전체 추천 결과가 포함된다. `state`는 `queued`, `running`, `done`, `error` 중 하나이며, `error` 상태에서는 오류 메시지가 반환된다. 서버에 `MOVAR_DEMO_KEY`가 설정된 경우 요청 헤더 `X-Movar-Demo-Key`에 동일한 키를 전달한다.
