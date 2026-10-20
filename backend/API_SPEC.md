# MOVAR API 명세

## 구현 현황

| 엔드포인트 | 상태 | 인증 | 설명 |
| --- | --- | --- | --- |
| `GET /health` | 구현 | 없음 | 서버 실행 상태 |
| `GET /health/db` | 구현 | 없음 | Supabase DB 실제 조회로 연결 확인 |
| `GET /products?limit=` | 구현 | 없음 | 제품 목록(연결 검증용), limit 1~100 |
| `GET /me` | 구현 | 필요 | 로그인 토큰 검증 확인 |
| `POST /analysis-reports` | 구현 | 없음(추후 필요) | 사진 한 장으로 분석 → 제품 추천 → LLM 리포트까지 한 번에 생성 |
| `POST /scalp-analyses` | 구현 | 없음(추후 필요) | 두피 사진 1장으로 증상 6개 단계 분석 (이미지 모델 서버 연동) |
| `POST /recommendations` | 구현 | 없음(추후 필요) | 두피 증상 기반 상품 추천 (팀 추천 모델 서버 연동) |
| `POST /reports/mock` | 구현 (목업) | 없음 | 가짜 AI 분석·추천 + 실제 LLM 문구로 리포트 생성 |
| `POST /reports` | 구현 | 없음(추후 필요) | 전달받은 분석 결과로 LLM 리포트 생성 |
| `GET /hospitals` | 구현 | 없음 | 현재 위치 기준 주변 병원 검색 (카카오 로컬 API) |
| `GET /dashboard` | 미구현 (아래 초안) | 필요 | 대시보드 조회 |
| 문진, 결과 저장·조회 | 미구현 | | 담당과 합의 후 정의 |

공통 사항
- 인증은 Supabase Auth를 사용합니다. 프론트가 `supabase-js`로 로그인하고, 받은 access token을
  `Authorization: Bearer <토큰>` 헤더로 보냅니다. backend는 Supabase Auth 서버로 토큰을 검증합니다.
- 오류 본문은 `{"detail": {"code": "...", "message": "..."}}` 형식입니다. 입력 검증 실패(422)만 FastAPI 기본 형식입니다.
- CORS는 `http://localhost:5173`, `http://127.0.0.1:5173`만 허용합니다. 다른 주소는 추가가 필요합니다.
- 서버 키(`SUPABASE_KEY`), `GEMINI_API_KEY`, `KAKAO_REST_API_KEY`, 추천 서버 주소(`MOVAR_API_BASE_URL`), 이미지 모델 서버 주소(`MOVAR_VISION_API_BASE_URL`)는
  backend의 `.env`에만 두며 프론트로 전달하지 않습니다.

## 프론트 호출 흐름 (현재 구현 기준)

한 번에 처리하려면 `POST /analysis-reports`(아래 참고) 하나만 호출하면 되고, 단계별로 보여 주려면 아래 2~4번을 순서대로 호출합니다.

1. 로그인: 프론트가 Supabase Auth로 직접 처리합니다. (backend 호출 없음)
2. 두피 분석: `POST /scalp-analyses`에 사진 1장을 올려 증상 6개(`symptoms`)를 받습니다.
3. 상품 추천: `POST /recommendations`에 2번의 `symptoms`와 카테고리를 보내 추천 상품을 받습니다.
4. 리포트: `POST /reports`에 2번과 **같은 `symptoms`**, 문진 답변, 3번에서 받은 상품을 보내 리포트를 받습니다.
   상품은 `product_id`, `product_name`, `brand_name`을 넘기며 추천 응답의 `brand`가 `brand_name`에 해당합니다.
5. 병원 찾기: 브라우저 위치 권한으로 얻은 좌표로 `GET /hospitals`를 호출합니다. 다른 단계와 독립적입니다.

비전 모델의 증상 6개(0~3)가 `/recommendations`와 `/reports` 두 곳에서 같은 형식으로 쓰입니다.
종합 케어 지수(`care_score`)는 산정 기준이 정해지지 않아 `/reports`에서 선택 항목입니다(아래 참고).

## 인증: GET /me

`Authorization: Bearer <access token>`을 검증하고 사용자 정보를 반환합니다. 로그인이 필요한 API는 같은 방식으로 보호합니다.

```json
{"id": "사용자 UUID", "email": "user@example.com"}
```

| 상태 | code | 의미 |
| --- | --- | --- |
| 401 | `AUTH_REQUIRED` | 토큰 없음 |
| 401 | `AUTH_INVALID_TOKEN` | 토큰 만료 또는 유효하지 않음 |
| 502 | `AUTH_INVALID_RESPONSE` | 인증 서버 응답 형식 오류 |
| 503 | `AUTH_NOT_CONFIGURED` / `AUTH_UNREACHABLE` / `AUTH_UPSTREAM_ERROR` | 설정 누락, 접속 불가, 인증 서버 오류 |
| 504 | `AUTH_TIMEOUT` | 인증 서버 응답 시간 초과 |

## 한 번에 생성: POST /analysis-reports

사진 한 장으로 두피 분석 → 제품 추천 → LLM 리포트를 backend가 차례로 실행하고 결과를 한꺼번에 반환합니다.
내부에서 `POST /scalp-analyses`, `POST /recommendations`, `POST /reports`와 같은 처리를 순서대로 부르므로 각 단계의 규칙과 오류 코드가 그대로 적용됩니다.
이미지 모델, 추천 모델(수 초), Gemini를 차례로 호출해서 **응답에 수십 초가 걸릴 수 있습니다.** 프론트에서 로딩 표시와 넉넉한 타임아웃이 필요합니다.
단계별로 결과를 먼저 보여 주고 싶으면 이 엔드포인트 대신 세 엔드포인트를 따로 호출합니다.

요청은 `multipart/form-data`입니다.

| 필드 | 형식 | 설명 |
| --- | --- | --- |
| file | 파일 (필수) | 두피 사진 1장. JPEG, PNG, WEBP, 10MB 이하 |
| categories | 문자열, 여러 번 지정 가능 | `shampoo`, `scaler`, `treatment`, `tonic`. 생략하면 `shampoo` |
| questionnaire | JSON 문자열 (선택) | `{"문항": "답변"}` 형식. 예: `{"세정 빈도": "하루 한 번"}`. 문자열 값만 허용 |

응답은 `{symptoms, recommendations, report}`입니다.

| 필드 | 의미 |
| --- | --- |
| symptoms | 이미지 모델이 분석한 증상 6개 단계(0~3) |
| recommendations | `POST /recommendations`의 `recommendations`와 같음(가격, 이미지, 구매 링크 포함) |
| report | `POST /reports`의 응답과 같음. `products`는 위 추천 제품 기준이며 제품 이름 200자, 브랜드 100자까지만 사용 |

- 추천 결과가 없으면 `recommendations`가 빈 배열이고 리포트의 `products`도 빈 배열입니다.
- 한 단계가 실패하면 그 단계의 오류가 그대로 반환되고 이후 단계는 실행하지 않습니다. 예를 들어 추천 서버가 꺼져 있으면 `RECOMMEND_UNREACHABLE`(503)이 나오고 LLM은 호출하지 않습니다.
- `care_score`는 없이 생성됩니다(null).
- 추천 요청은 카테고리만 보내며 `user_info`(연령, 세정 빈도, 최대 가격)는 아직 지원하지 않습니다.
- 현재 인증 검사가 없으며 호출마다 GPU 작업과 LLM 비용이 발생하므로 배포 전에 로그인 검사를 추가해야 합니다.

추가 오류: 422 `QUESTIONNAIRE_INVALID`(문진이 JSON 객체가 아니거나 너무 긺). 그 외 코드는 `IMAGE_*`, `VISION_*`, `RECOMMEND_*`, `LLM_*`와 같습니다.

## 두피 분석: POST /scalp-analyses

두피 사진 1장을 받아 이미지 모델 서버(`ai/inference`의 `/predict`)로 전달하고, 증상 6개의 단계(0~3)를 반환합니다.
요청은 `multipart/form-data`이며 파일 필드 이름은 `file`입니다. JPEG, PNG, WEBP만 허용하고 10MB 이하여야 합니다.
형식은 파일 내용으로 판별하므로 확장자나 `Content-Type`을 속여도 통과하지 않습니다. 사진은 저장하지 않고 이미지 모델 서버로 전달만 합니다.

응답: `{symptoms, model}`. `symptoms`는 `POST /recommendations`·`POST /reports`가 받는 형식과 같아서 그대로 넘기면 됩니다.

```json
{"symptoms": {"micro_keratin": 0, "excess_sebum": 2, "follicular_erythema": 1,
              "follicular_pustule": 0, "dandruff": 3, "hair_loss": 0},
 "model": "MOVAR-EUPE-V7-512"}
```

이미지 모델 서버는 증상별 점수(`class_scores`)도 주지만, 보정된 확률이 아니라서 응답에 포함하지 않습니다.
결과는 연구·참고용이며 의료 진단으로 표현하면 안 됩니다. 현재 인증 검사가 없으므로 배포 전에 로그인 검사를 추가해야 합니다.

| 상태 | code | 의미 |
| --- | --- | --- |
| 400 | `IMAGE_EMPTY` | 비어 있는 파일 |
| 413 | `IMAGE_TOO_LARGE` | 10MB 초과 |
| 415 | `IMAGE_UNSUPPORTED` | JPEG, PNG, WEBP가 아님 |
| 422 | `IMAGE_REJECTED` | 이미지 모델 서버가 분석할 수 없다고 거절(너무 작음, 깨진 파일 등). 파일 누락 시에는 FastAPI 기본 422 |
| 502 | `VISION_INVALID_RESPONSE` | 이미지 모델 서버 응답 형식 오류 |
| 503 | `VISION_NOT_CONFIGURED` / `VISION_UNREACHABLE` / `VISION_UPSTREAM_ERROR` | 주소 미설정, 접속 불가(서버 꺼짐), 서버 오류 |
| 504 | `VISION_TIMEOUT` | 분석 응답 시간 초과(60초) |

## 상품 추천: POST /recommendations

팀 추천 모델 서버(RunPod, Hybrid RAG + Qwen)에 작업을 등록하고, 완료될 때까지 backend가 대신 조회한 뒤 추천 상품을 반환합니다.
프론트는 이 엔드포인트 하나만 호출하면 되며 RunPod 주소를 알 필요가 없습니다(브라우저 직접 호출은 CORS 문제가 있어 backend가 중계합니다).
추천 서버 연동 규격은 `MOVAR_RAG_API 연동 가이드.md`를 따릅니다. 보통 수 초가 걸리며 최대 120초까지 기다립니다.

### 요청

| 필드 | 형식 | 설명 |
| --- | --- | --- |
| symptoms | object (필수) | 아래 6개 증상을 모두 포함. 각각 정수 0(없음)~3(가장 높음) |
| categories | array (필수, 1~4개) | `shampoo`, `scaler`, `treatment`, `tonic`. 선택한 전체에서 합쳐 최대 3개가 추천됨. 화면에서는 하나씩 요청하길 권장 |
| user_info | object (선택) | `age_group`(예: "20대"), `wash_frequency`(예: "하루 1회"), `max_price`(양의 정수, 원) |

symptoms 필드: `micro_keratin`(미세각질), `excess_sebum`(피지과다), `follicular_erythema`(모낭사이홍반),
`follicular_pustule`(모낭홍반농포), `dandruff`(비듬), `hair_loss`(탈모). 알레르기 입력·필터는 추천 서버에 아직 없습니다.

### 응답

`{recommendations, priority}`. priority는 우선 관리가 필요한 증상 코드 배열입니다.
후보가 없으면 recommendations가 빈 배열입니다.

| recommendations[] 필드 | 의미 |
| --- | --- |
| rank | 순위 (1~3) |
| product_id, product_name, brand | 제품 식별자, 이름, 브랜드 |
| category, category_kr | 카테고리 코드, 한글명(샴푸 등) |
| price, rating, reviews | 가격(원), 평점, 리뷰 수. null 가능 |
| image, link, volume | 이미지 URL, 구매 링크, 용량. null 가능 |
| reason | 추천 이유 |
| matched_symptoms | 이 제품이 대응하는 증상 코드 |

추천 서버의 내부 점수(`llm_score`)는 화면 노출 대상이 아니라서 응답에 포함하지 않습니다.
`price`, `image`, `link` 등이 null일 수 있으니 프론트에서 누락 처리가 필요합니다.

### 오류

| 상태 | code | 의미 |
| --- | --- | --- |
| 422 | (FastAPI 기본) | 증상 누락·범위(0~3) 오류, 잘못된 카테고리 |
| 429 | `RECOMMEND_BUSY` | 추천 서버의 동시 작업 제한 초과. 잠시 후 재시도 |
| 502 | `RECOMMEND_JOB_FAILED` / `RECOMMEND_JOB_LOST` / `RECOMMEND_UPSTREAM_ERROR` / `RECOMMEND_INVALID_RESPONSE` | 추천 작업 실패, 작업 소실(서버 재시작), 요청 거절, 응답 형식 오류 |
| 503 | `RECOMMEND_NOT_CONFIGURED` / `RECOMMEND_UNREACHABLE` / `RECOMMEND_UPSTREAM_ERROR` | 주소 미설정, 추천 서버 접속 불가(Pod 중지 가능), 서버 오류 |
| 504 | `RECOMMEND_TIMEOUT` | 응답 대기 시간 초과 |

추천 서버 주소는 Pod를 다시 만들면 바뀝니다. 바뀌면 backend `.env`의 `MOVAR_API_BASE_URL`만 갱신하고 서버를 재시작합니다.
현재 인증 검사가 없으며 호출이 추천 서버의 GPU 작업으로 이어지므로, 배포 전에 로그인 검사를 추가해야 합니다.

## 리포트: POST /reports, POST /reports/mock

AI 두피 분석 리포트(시안: 케어 지수, 요약, 증상별 상태, 맞춤 케어 가이드, 관리 루틴, 제품 추천)를 생성합니다.
증상 단계(0~3)는 AI 분석이 정한 값이며 LLM(Gemini)은 문구만 작성합니다. 단계는 그대로 반환합니다.
두피 상태 이미지는 포함하지 않습니다.

- `POST /reports/mock`: AI 모델 완성 전 흐름 확인용입니다. 분석 결과(케어 지수 76, 피지과다 2, 모낭사이홍반 1, 나머지 0)와
  추천 제품(DB의 앞쪽 제품 2개)은 목업이며 맞춤 결과가 아닙니다. 문구만 실제로 생성됩니다.
- `POST /reports`: 호출하는 쪽이 분석 결과를 직접 전달합니다. 현재 인증 검사가 없으며 호출마다 LLM 비용이 발생하므로 배포 전에 로그인 검사를 추가해야 합니다.

### 요청

`/reports/mock`의 본문은 문진 답변만 담은 객체입니다(생략 가능). 예: `{"세정 빈도": "하루 한 번"}`

`/reports`의 본문:

| 필드 | 형식 | 설명 |
| --- | --- | --- |
| symptoms | object (필수) | `POST /recommendations`와 같은 6개 증상(`micro_keratin`, `excess_sebum`, `follicular_erythema`, `follicular_pustule`, `dandruff`, `hair_loss`). 각각 정수 0~3 |
| care_score | integer 0~100 (선택) | 종합 두피 케어 지수. 산정 기준이 정해지기 전에는 생략 가능하며, 생략하면 점수 없이 리포트가 만들어짐 |
| questionnaire | object | 문진 문항 → 답변 (최대 20개, 답변 300자 이내). 생략 가능 |
| products | array(최대 5) | `{product_id, product_name, brand_name}`. 맞춤 추천 단계에서 정해진 제품. 생략 가능 |

### 응답

| 필드 | 형식 | 의미 |
| --- | --- | --- |
| analyzed_at | ISO 8601 string | 리포트 생성 일시 (KST, +09:00) |
| care_score | integer 또는 null | 요청의 케어 지수. 요청에서 생략하면 null |
| headline | string | 상단 제목 (예: "피지 관리가 필요해요") |
| headline_text | string | 제목 아래 설명 |
| summary | string | AI 분석 요약 |
| conditions | array(6) | 증상 6개 모두 `{code, label, level, description}`. level은 요청의 증상 단계(0~3), label은 미세각질·피지과다·모낭사이홍반·모낭홍반농포·비듬·탈모. 단계 0은 이상 없음 문구. 화면에서 level이 높은 것만 골라 보여줄 수 있음 |
| care_guides | array(3) | 맞춤 케어 가이드 `{title, description}` |
| routine | object | `morning`, `evening` 문자열 배열. 시안의 "오후" 칸에 `evening`을 표시 |
| products | array | `{product_id, product_name, brand_name, description}`. 요청에 없던 제품은 나오지 않음 |
| disclaimer | string | 고정 면책 문구 (서버가 삽입) |

### 오류

| 상태 | code | 의미 |
| --- | --- | --- |
| 422 | (FastAPI 기본) | 입력 검증 실패 (증상 누락·범위 0~3 오류, 지수 범위 등) |
| 502 | `LLM_INVALID_RESPONSE` | LLM 응답이 정해진 형식이 아님 |
| 503 | `LLM_NOT_CONFIGURED` / `LLM_UPSTREAM_ERROR` / `LLM_UNREACHABLE` | 설정 누락, LLM 호출 실패, 접속 불가 |
| 504 | `LLM_TIMEOUT` | LLM 응답 시간 초과(60초) |

응답은 호출마다 LLM이 새로 생성하며 저장되지 않습니다. 저장·재조회 API는 아직 없습니다.

## 병원 찾기: GET /hospitals

카카오 로컬 API로 현재 위치 주변의 병원을 가까운 순으로 검색합니다. 로그인 없이 호출할 수 있습니다.
프론트는 브라우저 위치 권한으로 얻은 위도·경도를 넘깁니다. 위치를 거부한 경우 쓸 지역명 검색은 아직 없습니다.
지도 표시는 응답의 `lat`, `lng`를 프론트 지도에 찍는 방식이며, 카카오 REST API 키는 backend에만 둡니다.

| 쿼리 | 형식 | 설명 |
| --- | --- | --- |
| lat | number (필수) | 위도 |
| lng | number (필수) | 경도 |
| radius | integer 100~20000 | 검색 반경(m), 기본 5000 |
| query | `피부과` 또는 `탈모` | 검색 키워드, 기본 `피부과` |
| size | integer 1~15 | 결과 개수, 기본 15 |

응답은 `{items, total}`입니다. items의 각 항목은 아래 필드를 가지며 값이 없으면 null입니다.

| 필드 | 의미 |
| --- | --- |
| name, category | 병원명, 카카오 분류 |
| address, road_address | 지번·도로명 주소 |
| phone | 전화번호 |
| distance_m | 현재 위치로부터의 거리(m) |
| lat, lng | 좌표 |
| place_url | 카카오맵 상세 페이지 링크 |

오류: 422(좌표 누락·범위 오류), 502 `HOSPITAL_INVALID_RESPONSE`, 503 `HOSPITAL_NOT_CONFIGURED` /
`HOSPITAL_UPSTREAM_ERROR` / `HOSPITAL_UNREACHABLE`, 504 `HOSPITAL_TIMEOUT`.
카카오 검색 결과는 키워드에 맞는 장소이며 진료과목이나 영업 여부를 보증하지 않습니다.

# 대시보드 API 초안

사용자가 공유한 대시보드 시안을 기준으로 정리한 제안입니다.
아래 `/dashboard`는 아직 구현되지 않았으며 프론트·AI·DB 담당과 합의할 계약 초안입니다.

## 화면 범위

| 화면 영역 | 서버에서 제공할 정보 |
| --- | --- |
| 사용자 표시 | 로그인 여부, 닉네임 |
| 최근 두피 상태 | 최근 분석 ID·일시, 케어 지수, 상태 제목·설명 |
| 유분·각질·붉은기 | 항목 식별자·이름, 등급, 표시용 수치 |
| 헤어케어 상품 추천 | 제품·옵션 ID, 제품명, 이미지 URL, 구매 링크 |

로고, 메뉴, 고정 촬영 배너, AI 에이전트 소개, 사용방법은 프론트의 고정 콘텐츠로 둡니다.
촬영·분석 결과·맞춤 케어·변화 기록 버튼은 해당 화면으로 이동합니다.
대시보드 시안에 없는 사진 전송과 문진 입력 형식은 후속 화면을 기준으로 정합니다.

## 제안: GET /dashboard

대시보드에 필요한 현재 사용자와 최근 분석·추천 정보를 한 번에 조회합니다.
요청 본문은 없습니다. 로그인 사용자는 향후 확정할 인증 정보로 식별하며,
클라이언트가 지정한 임의의 사용자 ID로 다른 사람의 결과를 조회하게 만들지 않습니다.
인증은 Supabase Auth로 정했으며 위 `GET /me`와 같은 방식으로 토큰을 검증합니다.

### 응답 필드

| 필드 | 형식 | 의미 |
| --- | --- | --- |
| user | object | is_guest(boolean), nickname(string 또는 null) |
| latest_analysis | object 또는 null | 분석 기록이 없거나 게스트면 null |
| latest_analysis.analysis_id | integer | 분석 결과 상세 화면에서 사용할 ID |
| latest_analysis.analyzed_at | ISO 8601 string | 분석 일시, 시간대 포함 |
| latest_analysis.care_score | number 또는 null | 화면의 케어 지수. 계산 전에는 null |
| latest_analysis.summary_title | string 또는 null | 상태 제목 |
| latest_analysis.summary_text | string 또는 null | 설명 문구 |
| latest_analysis.conditions | array | 각 항목의 code, label, grade, display_value |
| recommended_products | array | 최근 분석에 연결된 추천 제품. 없으면 빈 배열 |

conditions의 code 초안은 `oil`, `flakes`, `redness`이며,
label은 각각 유분·각질·붉은기입니다. AI 모델의 출력 항목과 대응 관계를 확정해야 합니다.
grade는 문자열 또는 null, display_value는 숫자 또는 null입니다.
점수 범위·등급 기준·막대 표시 척도는 미정이며 임의로 0~100 변환하지 않습니다.

recommended_products의 각 항목은 `product_id`, `variant_id`, `product_name`,
`image_url`, `product_url`을 가집니다. 이미지·링크가 없으면 null을 반환하고
프론트는 대체 이미지나 링크 비활성화로 처리합니다.
제품 목록을 임의로 가져온 결과는 맞춤 추천으로 표시하지 않습니다.

### 게스트 / 분석 기록 없음

```json
{
  "user": {"is_guest": true, "nickname": null},
  "latest_analysis": null,
  "recommended_products": []
}
```

로그인했지만 분석 기록이 없는 경우에도 latest_analysis는 null입니다.
프론트는 점수 0이나 샘플 점수 76 대신 분석 시작 안내를 보여줍니다.
제공된 시안의 76점, 상태 문구, 추천 제품은 화면 예시이며 실제 분석 결과가 아닙니다.

### 오류 처리 초안

- 200: 정상 응답. 기록이 없어도 위 빈 상태를 반환합니다.
- 401: 전달된 인증 정보가 만료되었거나 유효하지 않습니다.
- 503: DB 또는 필요한 외부 서비스 조회가 불가능합니다.
- 504: 외부 서비스 응답 시간 초과입니다.

DB 장애를 분석 기록 없음으로 바꾸어 응답하지 않습니다.

## 현재 DB와 대응

| 정보 | 현재 저장 위치 / 결정할 사항 |
| --- | --- |
| 사용자 | public.users. 로그인 방식과 사용자 식별 연결은 미정 |
| 최근 분석 | scalp_analyses의 analysis_id, user_id, created_at |
| 점수·항목별 상태·설명 | analysis_result JSONB 내부 구조를 AI·DB 담당과 합의해야 함 |
| 추천 | recommendations → product_variants → products |
| 제품명·구매 링크 | products.product_name, products.product_url |
| 상품 이미지 | products.image (2026-10-16 확인) |

## 팀과 확인할 내용

1. 프론트: 위 응답 필드로 대시보드를 표시할 수 있는지, 빈 상태 표시 방식.
2. AI: 증상 6개(0~3)의 단계 의미, 종합 케어 지수(`care_score`)를 증상 단계에서 어떻게 산정할지(또는 지수를 없앨지).
3. 리포트·추천: 점수·요약 문구 생성 담당, 추천 결과의 variant_id 제공 여부.
4. DB: analysis_result JSON 구조, 상품 이미지 저장 위치, 인증 방식과 users 연결.

이번 문서는 대시보드 기준 초안 작성까지만 수행하며 DB 구조·데이터는 변경하지 않습니다.

## DB 담당에게 확인할 질문

2026-10-16에 읽기 전용으로 확인한 DB 상태입니다. `users`, `scalp_analyses`, `recommendations`는 행이 0개입니다.

1. 인증을 Supabase Auth로 정했는데 `users`는 `password_hash`가 필수인 자체 가입 구조입니다.
   `password_hash`를 선택으로 바꾸거나 없애고 Auth 사용자 ID(UUID)를 담는 컬럼(예: `auth_id`)을 추가해도 되는지,
   또는 자체 로그인으로 가는 것이 의도인지 확인이 필요합니다.
2. `scalp_analyses.user_id`는 숫자(bigint)입니다. Auth 사용자 ID(UUID)와 연결하는 방법을 정해야 합니다.
3. 문진 답변을 저장할 위치가 없습니다. `analysis_result`(JSONB)에 함께 넣을지, 컬럼·테이블을 추가할지 정해야 합니다.
4. LLM 리포트 본문을 저장할 위치도 없습니다. 같은 방식으로 정해야 합니다.
5. `analysis_result` JSON의 구조(케어 지수, 항목별 등급)를 AI 담당과 맞춰야 합니다.
6. `recommendations`는 `variant_id`로 제품 옵션에 연결됩니다. AI의 추천 결과가 variant 단위로 나오는지 확인이 필요합니다.
7. 촬영 이미지는 `scalp_analyses.image_paths`(text 배열)에 경로로 저장하는 구조로 보입니다. 저장소(Supabase Storage 등)와 접근 권한을 정해야 합니다.
