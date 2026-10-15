# MOVAR 대시보드 API 명세 초안

사용자가 공유한 대시보드 시안을 기준으로 정리한 제안입니다.
아래 `/dashboard`는 아직 구현되지 않았으며 프론트·AI·DB 담당과 합의할 계약 초안입니다.
현재 구현된 API는 `/health`, `/health/db`, `/products`입니다.

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
인증 수단(Supabase Auth 또는 별도 인증)은 미정입니다.

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
| 상품 이미지 | 현재 전용 컬럼 없음. 저장 위치 또는 외부 공급원 합의 필요 |

## 팀과 확인할 내용

1. 프론트: 위 응답 필드로 대시보드를 표시할 수 있는지, 빈 상태 표시 방식.
2. AI: 유분·각질·붉은기와 모델 출력의 대응, 심각도 단계의 의미.
3. 리포트·추천: 점수·요약 문구 생성 담당, 추천 결과의 variant_id 제공 여부.
4. DB: analysis_result JSON 구조, 상품 이미지 저장 위치, 인증 방식과 users 연결.

이번 문서는 대시보드 기준 초안 작성까지만 수행하며 DB 구조·데이터는 변경하지 않습니다.
