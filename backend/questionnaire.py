"""Intake questionnaire: the question list the frontend renders, answer validation, and how answers feed the other steps."""
import json
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel

from recommend import UserInfo


class Option(BaseModel):
    value: str
    label: str


class Question(BaseModel):
    id: str
    label: str
    type: Literal['single', 'multi']
    options: list[Option]


def _opts(*labels: str) -> list[Option]:
    return [Option(value=label, label=label) for label in labels]


# Values of age_group and wash_frequency are sent to the recommendation model as they are.
QUESTIONS: list[Question] = [
    Question(id='age_group', label='연령대를 알려주세요', type='single',
             options=_opts('10대', '20대', '30대', '40대', '50대 이상')),
    Question(id='wash_frequency', label='샴푸는 얼마나 자주 하나요?', type='single',
             options=_opts('하루 2회 이상', '하루 1회', '이틀에 1회', '주 2~3회')),
    Question(id='dry_method', label='머리는 어떻게 말리나요?', type='single', options=[
        Option(value='cool_dryer', label='드라이기 찬바람'),
        Option(value='hot_dryer', label='드라이기 뜨거운 바람'),
        Option(value='natural', label='자연 건조'),
    ]),
    Question(id='sweat', label='땀이 많이 나는 활동(운동 등)은 얼마나 하나요?', type='single', options=[
        Option(value='rare', label='거의 안 해요'),
        Option(value='sometimes', label='주 1~3회'),
        Option(value='often', label='주 4회 이상'),
    ]),
    Question(id='styling', label='스타일링 제품(왁스, 스프레이 등)을 사용하나요?', type='single', options=[
        Option(value='never', label='거의 안 써요'),
        Option(value='sometimes', label='가끔 써요'),
        Option(value='often', label='자주 써요'),
    ]),
    Question(id='concerns', label='요즘 두피 고민을 모두 골라주세요', type='multi', options=[
        Option(value='itch', label='가려움'),
        Option(value='oily', label='번들거림'),
        Option(value='flakes', label='각질·비듬'),
        Option(value='redness', label='붉어짐·열감'),
        Option(value='hair_loss', label='머리카락 빠짐'),
        Option(value='none', label='특별한 고민 없음'),
    ]),
    Question(id='budget', label='샴푸 등 제품 예산은 어느 정도인가요?', type='single', options=[
        Option(value='under_10000', label='1만원 이하'),
        Option(value='under_20000', label='2만원 이하'),
        Option(value='under_30000', label='3만원 이하'),
        Option(value='any', label='상관없어요'),
    ]),
]

_BY_ID = {q.id: q for q in QUESTIONS}
_BUDGET = {'under_10000': 10_000, 'under_20000': 20_000, 'under_30000': 30_000}

Answers = dict[str, str | list[str]]


def _invalid(message: str) -> HTTPException:
    return HTTPException(422, {'code': 'QUESTIONNAIRE_INVALID', 'message': message})


def parse_answers(raw: str | None) -> Answers:
    """Parse and validate a JSON string like {"age_group": "20대", "concerns": ["oily"]}. Missing answers are allowed."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        raise _invalid('문진 답변은 JSON 문자열이어야 합니다.') from None
    if not isinstance(data, dict):
        raise _invalid('문진 답변은 {"문항 id": "답변"} 형식이어야 합니다.')

    answers: Answers = {}
    for qid, value in data.items():
        question = _BY_ID.get(qid)
        if question is None:
            raise _invalid(f'알 수 없는 문항입니다: {qid}')
        allowed = {o.value for o in question.options}
        if question.type == 'single':
            if not isinstance(value, str) or value not in allowed:
                raise _invalid(f'"{qid}" 문항의 답변이 올바르지 않습니다.')
        else:
            if not isinstance(value, list) or not all(isinstance(v, str) and v in allowed for v in value):
                raise _invalid(f'"{qid}" 문항의 답변이 올바르지 않습니다.')
            if len(set(value)) != len(value):
                raise _invalid(f'"{qid}" 문항에 같은 답변이 중복되었습니다.')
        answers[qid] = value
    return answers


def to_user_info(answers: Answers) -> UserInfo | None:
    """The part of the answers the recommendation model understands."""
    info = UserInfo(
        age_group=answers.get('age_group'),
        wash_frequency=answers.get('wash_frequency'),
        max_price=_BUDGET.get(answers.get('budget', '')),
    )
    return info if info.model_dump(exclude_none=True) else None


def to_report_answers(answers: Answers) -> dict[str, str]:
    """Question label -> answer label, as readable text for the LLM report."""
    result = {}
    for qid, value in answers.items():
        question = _BY_ID[qid]
        labels = {o.value: o.label for o in question.options}
        values = value if isinstance(value, list) else [value]
        if values:
            result[question.label] = ', '.join(labels[v] for v in values)
    return result
