# MOVAR DB 요청 문서 (초안)

backend가 사용자별 기록(문진, 분석, 추천, 리포트)을 저장하고 보여 주려면 DB에 무엇이 필요한지 정리한 문서입니다.
**DB 담당이 검토하고 수정하는 것을 전제로 한 제안입니다.** 아래 SQL은 합의용 초안이며 아직 어디에도 실행하지 않았습니다.
현재 구조는 2026-10-20에 Supabase Data API 스키마를 읽기 전용으로 조회해 확인했습니다. 컬럼의 제약 조건(고유키, 외래키 등)과 RLS 설정은 이 방법으로 알 수 없어서 DB 담당의 확인이 필요합니다.

## 1. 왜 필요한가

화면에서 막혀 있는 기능이 전부 "저장된 기록"을 필요로 합니다.

| 화면 | 필요한 데이터 |
| --- | --- |
| 대시보드 (최근 두피 상태, 최근 분석, 상품 추천 카드) | 로그인한 사용자의 가장 최근 분석, 그 분석의 추천 제품 |
| 분석 결과 | 과거 분석 결과와 리포트 다시 보기 |
| 변화 기록 | 사용자의 분석 이력(날짜순)과 증상 변화 |

## 2. 서비스 흐름과 저장 시점

```
로그인(Supabase Auth) → 문진 → 사진 → 이미지 모델(증상 6개 0~3) → 추천 모델(제품 최대 3개) → LLM 리포트
```

한 번의 진단(위 흐름 한 바퀴)을 `scalp_analyses` 한 행으로 보고, 그 행에 문진·증상·사진·추천·리포트가 붙는 구조를 제안합니다.

## 3. 현재 DB (2026-10-20 확인)

| 테이블 | 행 수 | 주요 컬럼 |
| --- | --- | --- |
| `users` | 1 | user_id(bigint), email(필수), **password_hash(필수)**, nickname |
| `scalp_analyses` | 0 | analysis_id, user_id(bigint), scalp_type, hair_type, image_paths(text[]), analysis_result(jsonb, 필수) |
| `recommendations` | 0 | recommendation_id, analysis_id, **variant_id(필수)**, rank, score, reason |
| `products` | 145 | product_id, product_name, brand_name, price, rating, reviews, image, link, symptom_tags 등 |
| `product_variants`, `ingredients`, `variant_ingredients` | 166 / 1,285 / 6,667 | 제품 옵션과 성분 |

제품 테이블은 이미 채워져 있어 추천 화면에 필요한 이미지·가격·링크가 있습니다. 문제는 사용자와 분석 쪽입니다.

## 4. 현재 구조와 맞지 않는 점

1. **`users`가 Supabase Auth와 연결되지 않습니다.** 로그인은 Supabase Auth로 하기로 했는데, `users`는 숫자 ID와 `password_hash`가 필수인 자체 가입 구조입니다. Auth의 사용자 ID는 UUID라서 `scalp_analyses.user_id`(bigint)에 바로 넣을 수 없습니다.
2. **`recommendations`가 제품 옵션(`variant_id`)에 묶여 있습니다.** 추천 모델은 `product_id`와 카테고리, 순위, 추천 이유, 대응 증상을 돌려주고 `variant_id`는 주지 않습니다. `variant_id`가 필수인 한 추천 결과를 저장할 수 없습니다.
3. **증상 6개가 컬럼으로 없습니다.** `analysis_result`(JSON) 안에 넣을 수는 있지만, 변화 기록처럼 날짜별로 증상 단계를 비교·정렬하는 조회에는 컬럼이 낫습니다.
4. **문진 답변, LLM 리포트, 케어 지수를 저장할 곳이 없습니다.**
5. **촬영 사진 저장소가 정해지지 않았습니다.** `image_paths`(text[])만 있고 어디에 저장하는지, 누가 볼 수 있는지가 없습니다.
6. `scalp_type`, `hair_type` 컬럼의 용도를 알 수 없습니다. 이미지 모델이나 문진에서 채워지는 값이 없습니다. 용도를 알려 주세요.

## 5. 제안 구조

### 5.1 `users` ↔ Supabase Auth 연결 (결정 필요)

| 선택 | 내용 |
| --- | --- |
| **A (권장)** | `users`를 유지하고 `auth_id uuid`(Auth 사용자 ID)를 추가. `password_hash`는 선택으로 바꾸거나 삭제. 가입 시 `users` 행을 트리거로 자동 생성 |
| B | `users`를 폐기하고 Auth 사용자 UUID를 키로 하는 `profiles` 테이블(닉네임 등)을 새로 만듦. `scalp_analyses.user_id`를 uuid로 변경 |

현재 `users`에 1행이 있습니다. 이 행의 용도(테스트인지 실제 데이터인지)를 확인해 주세요.
A안에서는 backend가 토큰으로 얻은 Auth UUID를 `users.auth_id`로 찾아 내부 `user_id`로 바꿔 씁니다.

```sql
alter table public.users
  add column auth_id uuid unique references auth.users(id) on delete cascade,
  alter column password_hash drop not null;

create function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.users (auth_id, email, nickname)
  values (new.id, new.email, split_part(new.email, '@', 1));
  return new;
end $$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
```

### 5.2 `scalp_analyses` (한 번의 진단)

증상 6개는 이미지 모델의 `value_1~6` 순서와 같습니다. 단계는 0(없음)~3(가장 높음)입니다.

```sql
alter table public.scalp_analyses
  add column micro_keratin        smallint not null check (micro_keratin between 0 and 3),
  add column excess_sebum         smallint not null check (excess_sebum between 0 and 3),
  add column follicular_erythema  smallint not null check (follicular_erythema between 0 and 3),
  add column follicular_pustule   smallint not null check (follicular_pustule between 0 and 3),
  add column dandruff             smallint not null check (dandruff between 0 and 3),
  add column hair_loss            smallint not null check (hair_loss between 0 and 3),
  add column care_score           smallint check (care_score between 0 and 100),
  add column questionnaire        jsonb,
  add column model_version        text;

create index on public.scalp_analyses (user_id, created_at desc);
```

- `care_score`는 산정 기준이 아직 없어서 비어 있을 수 있습니다(`null` 허용).
- `questionnaire`에는 문진 답변을 문항 id 키로 그대로 저장합니다. 예: `{"age_group": "20대", "concerns": ["oily", "flakes"]}`. 문항과 선택지는 `API_SPEC.md`의 "문진"을 참고하세요.
- `analysis_result`(기존 필수 JSON)에는 이미지 모델의 원본 출력(증상별 점수 등)을 넣는 용도로 제안합니다.
- 위 `not null`은 테이블이 비어 있다는 전제입니다.

### 5.3 `recommendations`

```sql
alter table public.recommendations
  add column product_id         bigint references public.products(product_id),
  add column category           text,
  add column matched_symptoms   text[],
  alter column variant_id drop not null;
```

- 추천 모델이 주는 값을 저장합니다: 순위(`rank`), 추천 이유(`reason`), 카테고리(`shampoo` 등), 대응 증상(`matched_symptoms`).
- 가격, 이미지, 링크는 저장하지 않고 `products`에서 조회합니다(가격이 바뀔 수 있어서). 필요하면 추천 시점의 가격만 따로 저장할 수 있습니다.
- `score`에는 추천 모델의 내부 점수를 넣을 수 있으나, 화면에는 쓰지 않습니다.

### 5.4 `reports` (새 테이블)

```sql
create table public.reports (
  report_id    bigint generated always as identity primary key,
  analysis_id  bigint not null unique references public.scalp_analyses(analysis_id) on delete cascade,
  content      jsonb not null,
  llm_model    text,
  created_at   timestamptz not null default now()
);
```

`content`에는 `POST /reports` 응답 전체(헤드라인, 요약, 증상별 설명, 케어 가이드, 루틴, 제품 설명, 면책 문구)를 JSON으로 저장합니다. 목록 화면에서 자주 쓰는 `headline` 등은 JSON에서 꺼내 쓰면 됩니다.

### 5.5 촬영 사진 (결정 필요)

- 제안: Supabase Storage의 **비공개** 버킷(예: `scalp-images`)에 `{auth_id}/{analysis_id}/{파일명}` 경로로 저장하고, 경로를 `scalp_analyses.image_paths`에 기록합니다. 화면에는 짧은 유효기간의 서명 URL로 보여 줍니다.
- 지금 backend는 사진을 **저장하지 않고** 이미지 모델 서버로 전달만 합니다. 사진을 저장할지 자체가 결정 사항입니다. 두피 사진은 민감한 개인 정보라서 보관 여부, 보관 기간, 계정 삭제 시 삭제 방식을 팀이 정해야 합니다.

### 5.6 접근 권한 (RLS)

- 사용자 기록 테이블(`scalp_analyses`, `recommendations`, `reports`)은 **RLS를 켜고 본인 행만** 읽을 수 있게 합니다. `products` 계열은 모두에게 읽기를 허용합니다.
- backend가 쓰는 서버 키(service role)는 RLS를 우회합니다. 그래서 backend 코드에서도 모든 조회에 사용자 조건을 거는 것을 원칙으로 합니다. RLS는 그 뒤의 안전장치입니다.
- 정책 예시(A안 기준, 다른 테이블도 같은 방식으로 `analysis_id`를 따라가며 적용):

```sql
alter table public.scalp_analyses enable row level security;

create policy "own analyses" on public.scalp_analyses
  for select to authenticated
  using (user_id = (select u.user_id from public.users u where u.auth_id = auth.uid()));
```

## 6. backend가 만들 API와 사용하는 데이터

아래 API는 **이미 구현되어 있지만 서버 메모리의 임시 저장소를 씁니다**(`history.py`). 서버를 재시작하면 기록이 사라지고, 로그인하지 않은 사용자는 하나의 공용 목록을 공유합니다.
위 구조가 정해지면 응답 형식은 그대로 두고 저장·조회 부분만 아래 테이블을 쓰도록 바꿉니다. 응답 필드는 `API_SPEC.md`의 "대시보드와 변화 기록"을 따릅니다.

| API | 하는 일 | 읽고 쓰는 테이블 |
| --- | --- | --- |
| `POST /analysis-reports` (기존) | 분석·추천·리포트 생성 후 **저장** 추가 | 쓰기: scalp_analyses, recommendations, reports |
| `GET /dashboard` | 최근 분석 1건과 추천 제품, 사용자 닉네임 | users, scalp_analyses, recommendations, reports, products |
| `GET /analyses` | 분석 이력 목록(날짜, 증상 단계) → 변화 기록 | scalp_analyses |
| `GET /analyses/{id}` | 과거 분석 한 건의 상세와 리포트 | scalp_analyses, recommendations, reports, products |

모든 API는 로그인한 사용자 본인의 기록만 조회합니다. 클라이언트가 다른 사람의 ID를 지정해서 조회하는 경로는 만들지 않습니다.

## 7. DB 담당에게 확인할 것

1. `users`를 A안(Auth 연결 컬럼 추가)과 B안(`profiles`로 교체) 중 어느 쪽으로 할지. 현재 있는 1행의 용도.
2. `scalp_analyses.user_id`를 bigint로 유지할지, UUID로 바꿀지(B안이면 필수).
3. `recommendations.variant_id`를 선택으로 바꾸고 `product_id` 컬럼을 추가해도 되는지. 아니면 추천 모델이 `variant_id`를 줄 수 있는지.
4. `scalp_type`, `hair_type`은 무엇을 담는 컬럼인지, 지금 코드에서 채울 값이 있는지.
5. 사진을 저장할지, 저장한다면 버킷과 보관 기간, 계정 삭제 시 삭제 방식.
6. RLS가 이미 설정되어 있는지, 현재 `users`·`scalp_analyses` 등에 걸린 정책이 있는지.
7. 제품 수가 2026-10-16에 241건이던 기록과 달리 145건입니다. 의도한 변경인지.
8. 증상 컬럼을 위 제안대로 6개 `smallint`로 둘지, JSON에 두고 조회 시 꺼내 쓸지.

## 8. 변경 순서 제안

1. 위 7번 질문에 대한 합의
2. 스키마 변경(5.1~5.4), RLS 정책(5.6)
3. (사진을 저장하기로 했다면) 버킷 생성과 접근 정책
4. backend에서 저장 로직과 `/dashboard`, `/analyses` 구현

테이블이 비어 있는 지금이 구조를 바꾸기 가장 쉬운 시점입니다. 데이터가 쌓인 뒤에는 변경 비용이 커집니다.
