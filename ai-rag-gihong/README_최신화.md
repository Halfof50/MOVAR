# 실행 준비

## 1. 가상환경 생성

```powershell
python -m venv venv
```

## 2. 가상환경 실행

```powershell
.\venv\Scripts\activate
```

## 3. 패키지 설치

```powershell
pip install -r recommendation/requirements.txt
```

## 4. Gemma 준비

```powershell
ollama pull gemma3:12b
```

## 5. Vector Index 생성

최초 실행 또는 상품 데이터 / Embedding 관련 내용이 변경된 경우:

```powershell
python -m recommendation.build_index
```

## 6. 실행

사용자 직접 입력 테스트:

```powershell
python -m recommendation.interactive_recommend
```

또는 `interactive_recommend.py`를 열고 **Run Python File** 실행.

추천 서비스 단독 실행:

```powershell
python -m recommendation.service.recommendation_service
```

LLM 테스트:

```powershell
python -m recommendation.samples4 --model gemma3:12b
```

검색 단계 평가:

```powershell
python -m recommendation.evaluate
```

---

# 상품 추천 — 로컬 RAG

두피 분석 결과(증상 6종 × Level 0~3)를 받아 사용자에게 맞는 두피·헤어케어 상품을 추천한다.

검색 단계는 로컬 벡터 인덱스를 사용하고, 후보 상품의 개인화 적합도 평가는 **Gemma 3 12B** 로컬 LLM(Ollama)이 담당한다.  
최종 정렬, 실제 `product_id` 연결, 상품 정보 결합, 추천 이유 생성은 Python 코드가 담당한다.

외부 상품 API는 사용하지 않는다.  
LLM 리포트 생성은 별도 모듈이며 이 폴더의 상품 추천 RAG와 분리되어 있다.

현재 추천용 LLM은 **`gemma3:12b`** 를 사용한다.  
임베딩 모델은 **`jhgan/ko-sroberta-multitask`** 를 사용한다.

현재 추천용 Gemma는 별도 LoRA 파인튜닝 없이 사전학습 모델을 그대로 사용한다.

---

## 전체 파이프라인

카테고리 하나당 Gemma를 한 번 호출한다.

예를 들어 샴푸·토닉·트리트먼트를 추천해야 하면 각 카테고리에 대해 후보를 따로 검색하고 평가한다.

```text
Vision Model
두피 증상 6종 Level 0~3
        ↓
카테고리 결정
(report.product_plan.combo 또는 코드 규칙)
        ↓
카테고리별 반복
        │
        ├─ Query Builder
        │    증상 Level을 반영한 검색 문장 생성
        │
        ├─ Embedding
        │    jhgan/ko-sroberta-multitask
        │
        ├─ Vector Store
        │    같은 카테고리 안에서 코사인 유사도 기반 정확 탐색
        │
        ├─ Hybrid 후보 검색
        │
        ├─ 가격 등 코드 기반 조건 적용
        │
        ├─ 성분 적합도 / 근거 성분 결합
        │
        ├─ Gemma 3 12B
        │    후보 전체에
        │    0~100 적합도 점수 + decision_factors 부여
        │
        ├─ Python
        │    LLM 점수순 정렬 → Top 3 선택
        │
        ├─ Python
        │    후보 객체에서 실제 product_id / 상품정보 연결
        │
        └─ Python
             실제 score_evidence 기반 추천 이유 생성
        ↓
카테고리별 추천 결과 병합
```

핵심 역할 분리는 다음과 같다.

```text
RAG     = Embedding + 성분 적합도 기반 Hybrid 후보 검색
Gemma   = 후보별 개인화 적합도 판단
Python  = 정렬 + Top3 선정 + ID 매핑 + 검증 + 이유 생성
DB      = 상품 정보와 성분 근거의 사실 원천
```

---

## 성분 처리 흐름

상품을 바로 임베딩하는 것이 아니라, 먼저 전성분을 전처리하고 성분 근거를 만든다.

```text
상품 CSV
  ↓
전성분 표기 정규화
  ↓
같은 성분의 여러 표기 → 하나의 표준 성분으로 매핑
  ↓
증상별 성분 점수 계산
  ↓
symptom_scores / score_evidence 생성
  ↓
검색용 Product Document 생성
  ↓
Embedding
  ↓
Vector Store 저장
```

예:

```text
비오틴 / 바이오틴
        ↓
      비오틴

멘톨 / 엘-멘톨
        ↓
       멘톨
```

이 단계에서 이름이 비슷하지만 실제로 다른 성분은 강제로 같은 성분으로 합치지 않는다.

성분 매핑 결과는 이후 두 곳에서 사용한다.

1. 검색용 상품 Document의 주요 유효 성분·관리 목적 생성
2. Gemma의 후보 평가 및 최종 추천 이유의 검증된 근거

---

## RAG 검색

### Query Builder

사용자 두피 상태를 규칙 기반 문장으로 만든다.

예:

```text
탈모 Level 3
비듬 Level 1
```

↓

```text
탈모 관리가 가장 중요하고 비듬 관리도 필요한 두피.
탈모 관리를 우선하면서 비듬 관리에도 적합한 두피 케어 제품.
```

검색 Query는 LLM으로 만들지 않는다.

입력값이 증상 6종 × Level 0~3으로 고정되어 있기 때문에 규칙 기반으로 생성하는 편이 결과 재현성과 설명 가능성이 높다.

---

## Embedding

사용 모델:

```text
jhgan/ko-sroberta-multitask
```

Embedding 벡터는 L2 정규화하여 사용한다.

따라서 Vector Store에서는 정규화된 Query Vector와 Product Vector의 내적을 사용해 코사인 유사도를 계산할 수 있다.

코사인 유사도는 **최종 추천점수**가 아니다.

```text
코사인 유사도
    ↓
Embedding Top 12 + 성분 적합도 Top 3 → 중복 제거 후 최대 15개 후보
    ↓
Gemma가 후보들을 다시 평가
```

즉 RAG의 목적은 최종 1위를 결정하는 것이 아니라, 좋은 상품이 Gemma가 볼 후보 안에 들어오도록 하는 것이다.

현재 상품 수가 많지 않기 때문에 HNSW/IVF 같은 근사 탐색 대신 필터 적용 후 정확 탐색을 사용한다.

---

## Product Document

상품명만 임베딩하지 않는다.

검색용 Document에는 검색에 의미가 있는 정보를 조합한다.

예:

```text
상품명: A 두피케어 샴푸
카테고리: 샴푸
상품 설명: 탈모 증상 완화 기능성
주요 유효성분: 판테놀, 카페인, 살리실릭애씨드
주요 관리 목적: 탈모 관리, 두피 관리
```

반면 아래 정보는 검색용 텍스트보다는 Metadata로 관리한다.

```text
product_id
brand
price
rating
reviews
link
image
전체 전성분 원본
```

---

## Gemma 3 12B의 역할

이전 구조에서는 LLM이 후보 중 Top3를 직접 고르고 `product_id`까지 출력했다.

이 방식에서는 LLM이 실제 후보에 없는 ID를 생성할 가능성이 있었다.

현재 구조에서는 Gemma가 `product_id`를 출력하지 않는다.

Hybrid 검색으로 구성된 후보가 주어졌다면 다음처럼 **후보별 평가만 수행한다.**

```json
{
  "evaluations": [
    {
      "candidate_no": 1,
      "score": 82,
      "decision_factors": ["hair_loss", "dandruff"]
    },
    {
      "candidate_no": 2,
      "score": 71,
      "decision_factors": ["hair_loss"]
    }
  ]
}
```

Gemma의 역할:

- 후보 상품의 증상 적합성 비교
- 증상 Level 우선순위 반영
- 성분 적합도와 근거 성분 비교
- 제공된 사용자 정보가 실제 판단에 의미가 있을 때 반영
- 후보별 0~100 적합도 점수 부여
- 판단에 사용한 `decision_factors` 반환

Gemma가 하지 않는 것:

- `product_id` 생성
- 상품명 생성
- 최종 Top3 ID 직접 작성
- 가격/링크/이미지 등 DB 정보 생성
- 자유로운 추천 이유 생성
- 존재하지 않는 성분 효능 생성

---

## 최종 추천 선정

Gemma가 후보 전체에 점수를 반환하면 Python이 처리한다.

```text
후보 1 → 82점
후보 2 → 71점
후보 3 → 90점
...
        ↓
Python 점수순 정렬
        ↓
후보 3 → 후보 1 → 후보 2
        ↓
Top 3
```

실제 `product_id`와 상품명은 LLM 응답에서 가져오지 않는다.

Python이 원래 RAG 후보 객체에서 가져오기 때문에 LLM의 잘못된 상품 ID 생성 문제를 구조적으로 줄였다.

---

## 추천 이유

추천 이유도 Gemma가 자유롭게 작성하지 않는다.

Python이 상품 DB의 실제 데이터인 다음 값을 이용해 생성한다.

```text
symptom_scores
score_evidence
active_ingredients
```

예:

```text
탈모 관련 기준 성분: 판테놀, 비오틴, 나이아신아마이드.
비듬 관련 기준 성분: 살리실릭애씨드, 피록톤올아민.
```

따라서 사용자 화면에 표시되는 성분 근거는 LLM이 새로 만들어 낸 정보가 아니라 실제 상품 데이터에서 확인된 근거다.

---

## 증상 Level 0

증상 6종이 모두 Level 0이면 Gemma를 호출하지 않는다.

비교할 활성 증상이 없기 때문에 LLM에게 점수를 맡기기보다 코드의 순한 정도 기준으로 상품을 선택한다.

```text
전 증상 Level 0
      ↓
gentleness 기준
      ↓
Python Top3
```

---

## 구성

| 경로 | 역할 |
|---|---|
| `config.py` | 경로·모델명·상수 |
| `preprocessing/ingredient_normalizer.py` | 전성분 토큰화, 표기 변형 → 대표 성분명 |
| `preprocessing/ingredient_scores.py` | 증상별 성분 적합도 및 근거 생성 |
| `preprocessing/allergen_mapper.py` | 알레르기 관련 성분 매핑 |
| `preprocessing/product_document.py` | 검색용 Product Document와 레코드 생성 |
| `embedding/embedding_model.py` | SentenceTransformer 임베딩 |
| `embedding/vector_store.py` | 벡터·메타데이터 저장 및 코사인 유사도 검색 |
| `retrieval/query_builder.py` | 증상 Level → 검색 Query |
| `retrieval/retriever.py` | 후보 검색 및 성분 근거 결합 |
| `llm/recommendation_prompt.py` | Gemma 후보 평가 프롬프트 생성 |
| `llm/llama_client.py` | Ollama 호출 클라이언트 ※ 파일명은 기존 호환을 위해 유지 |
| `llm/output_parser.py` | Gemma 후보별 점수 검증 및 Python Top3 정렬 |
| `service/recommendation_service.py` | 카테고리 결정 및 전체 추천 파이프라인 연결 |
| `build_index.py` | 상품 Vector Index 생성 |
| `evaluate.py` | 검색 단계 평가 |
| `ablation.py` | Product Document 구성 비교 |
| `samples4.py` | LLM 후보 판단·순위 안정성 테스트 |

---

# 입출력

## 입력

```json
{
  "scalp_analysis": {
    "micro_keratin": 0,
    "excess_sebum": 0,
    "follicular_erythema": 0,
    "follicular_pustule": 0,
    "dandruff": 1,
    "hair_loss": 2
  },
  "user_profile": {
    "age_group": "30대",
    "wash_frequency": "하루 1회",
    "max_price": 60000
  },
  "plan": ["shampoo", "tonic"]
}
```

`plan`은 생략할 수 있다.

리포트 전체를 `report`로 전달하면 `product_plan.combo`에서 추천 카테고리를 읽는다.

```python
svc.recommend(
    scalp_analysis,
    user_profile,
    report=report,
)

svc.recommend(
    scalp_analysis,
    user_profile,
    plan=["shampoo", "scaler"],
)

svc.recommend(
    scalp_analysis,
    user_profile,
)
```

---

## Gemma 내부 평가 출력 예시

Gemma가 직접 상품 정보를 생성하는 것이 아니라 후보 번호별 평가를 반환한다.

```json
{
  "evaluations": [
    {
      "candidate_no": 1,
      "score": 86,
      "decision_factors": ["hair_loss", "dandruff"]
    },
    {
      "candidate_no": 2,
      "score": 72,
      "decision_factors": ["hair_loss"]
    }
  ]
}
```

---

## 최종 추천 결과 예시

```json
{
  "categories": ["shampoo"],
  "by_category": {
    "shampoo": {
      "candidate_count": 15,
      "candidate_ids": [53, 18, 31],
      "recommendations": [
        {
          "category_rank": 1,
          "product_id": 53,
          "product_name": "상품명",
          "category": "shampoo",
          "price": 15900,
          "rating": 4.55,
          "reviews": 11110,
          "retrieval_rank": 11,
          "similarity": 0.5715,
          "llm_score": 91,
          "candidate_no": 11,
          "decision_factors": ["hair_loss"],
          "symptom_scores": {
            "hair_loss": 1.0
          },
          "score_evidence": {
            "hair_loss": ["판테놀", "비오틴"]
          },
          "reason": "탈모 관련 기준 성분인 판테놀, 비오틴이 확인된 상품입니다.",
          "evidence_note": "탈모 판테놀, 비오틴"
        }
      ]
    }
  },
  "llm_available": true
}
```

`recommendations`는 모든 카테고리의 최종 추천을 합친 목록이다.

`by_category`는 제품 유형별 결과이며 `category_rank`가 해당 유형 안에서의 순위다.

---

# 설계 근거

## 1. 검색 Query를 LLM으로 만들지 않는다

입력이 증상 6종 × Level 0~3으로 고정되어 있으므로 규칙 기반 Query를 사용한다.

장점:

- 같은 입력 → 같은 Query
- 검색 결과 재현 가능
- 디버깅 가능
- 발표 시 설명 가능

---

## 2. 성분 매핑을 Embedding 전에 수행한다

제조사마다 다른 성분 표기를 먼저 표준 성분으로 매핑한다.

그 결과를 기반으로 유효 성분, 증상별 점수, 관리 목적을 만든 뒤 검색용 Document를 생성한다.

따라서 표기 차이 때문에 동일 성분이 누락되는 문제를 줄일 수 있다.

---

## 3. 코사인 유사도는 후보 검색에만 사용한다

코사인 유사도가 가장 높은 상품이 무조건 최종 추천 1위인 것은 아니다.

```text
Cosine Similarity
→ Embedding Top12 + 성분 적합도 Top3 → 최대 15개 후보

Gemma
→ 후보별 적합도 평가

Python
→ 점수순 Top3
```

따라서 검색 단계와 최종 추천 단계를 분리한다.

---

## 4. 성분 점수를 최종 공식 점수로 직접 사용하지 않는다

이전 구조처럼:

```text
성분 0.5 + 임베딩 0.3 + 평점 0.2
```

같은 임의 가중치 공식으로 최종 순위를 결정하지 않는다.

성분 점수는 Gemma가 판단할 수 있는 **검증된 근거 데이터**로 제공한다.

Gemma가 후보별 적합도를 판단하고 Python은 그 결과를 정렬한다.

---

## 5. LLM에게 product_id를 생성시키지 않는다

이전 방식:

```text
Gemma
→ Top3 선택
→ product_id 직접 출력
```

문제:

```text
후보 밖 product_id 생성
→ 검증 단계에서 제거
→ fallback 발생
```

현재 방식:

```text
Gemma
→ 후보번호별 점수

Python
→ 후보번호와 기존 객체 연결
→ 실제 product_id 사용
```

따라서 상품 ID는 DB에 존재하는 값을 그대로 사용한다.

---

## 6. 추천 이유를 LLM 자유생성에 맡기지 않는다

추천 이유는 `score_evidence`를 기반으로 코드에서 생성한다.

이를 통해:

- 존재하지 않는 성분 언급 감소
- 다른 상품의 성분 혼입 방지
- 추천 근거 재현 가능
- 결과 화면과 DB 근거 일치

를 목표로 한다.

---

## 7. 카테고리별로 LLM을 호출한다

샴푸 후보는 샴푸끼리, 토닉 후보는 토닉끼리 평가한다.

LLM이 서로 다른 카테고리의 역할까지 동시에 판단하지 않아도 되므로 비교 문제를 단순화할 수 있다.

대신 추천 카테고리가 많아질수록 LLM 호출 횟수와 응답 시간이 증가한다.

---

## 8. 전체 전성분을 매 요청마다 프롬프트에 넣지 않는다

전체 전성분은 DB/Metadata에 보존한다.

LLM 평가에는 이미 계산한 다음 정보가 주로 사용된다.

```text
유효 성분
증상별 성분 적합도
근거 성분
상품 설명
가격
평점
리뷰 수
검색 유사도
```

필요할 때만 `include_full_ingredients=True`로 전체 전성분을 확인할 수 있다.

---

# 현재 테스트 결과에서 확인된 점

Gemma 3 12B + 후보별 점수 방식에서 확인된 내용:

- 동일 입력 반복 안정성: 12/12 케이스 PASS
- LLM이 직접 product_id를 생성하지 않으므로 기존 후보 밖 ID 문제 제거
- 검색 Top3만 기계적으로 복사하지 않고 검색 하위 후보도 재평가
- 복합 증상에서 실제 성분 근거를 활용한 재정렬 확인
- 일부 복합 증상에서 점수 판단 기준을 추가 개선할 여지는 있음
- Hybrid 후보 전체를 평가하므로 후보 수에 따라 응답 시간이 증가할 수 있음

실서비스에서는 정확성과 안전성을 우선하고, 이후 필요하면 프롬프트 축소 또는 LLM 평가 후보 수 최적화를 통해 응답 시간을 줄인다.

---

# 한계

- 성분 함량을 반영하지 못한다. 전성분 표기에는 실제 함량이 제공되지 않는 경우가 많다.
- 전성분 표시 순서만으로 정확한 함량을 추정하지 않는다.
- 탈모 기능성 고시 성분 조합은 성분 포함 여부를 확인할 수 있지만 실제 농도 충족 여부까지 확인할 수 없는 경우가 있다.
- 음식 알레르기와 피부 도포 반응은 동일하다고 단정하지 않는다.
- 상품 데이터는 과제 시연 목적으로 자체 수집한 범위이며 지속적으로 추가·수정될 수 있다.
- 현재 Gemma 추천 모델은 LoRA 학습 전 기본 모델이다.
- 추천 결과는 의학적 진단이나 치료 지시가 아니라 참고용 제품 추천이다.

---

# 모델 정리

```text
Vision Model
→ 두피 증상 6종 Level 0~3

Embedding Model
→ jhgan/ko-sroberta-multitask

Local Recommendation LLM
→ Gemma 3 12B (Ollama: gemma3:12b)

Final Ranking
→ Gemma 후보별 점수 + Python 정렬

Recommendation Reason
→ Python + 실제 DB score_evidence

Report Generation
→ 별도 외부 LLM API
```
