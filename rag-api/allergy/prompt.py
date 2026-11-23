# -*- coding: utf-8 -*-
"""기존 2차 테스트에서 사용했던 판별 프롬프트 및 RAG 컨텍스트 형식."""
from __future__ import annotations
import json
from allergy.retriever import AllergyKB

SYSTEM_PROMPT = """너는 사용자 알레르기와 화장품 전성분 사이의 명시된 원료 관련성만 판정한다. 임상적 알레르기 발생이나 제품 안전성을 확정하지 않는다. 상품명은 판단 근거로 쓰지 않는다.
상품마다 다음 순서를 적용한다.
1) 사용자 알레르기 중 하나라도 해당 지정 접촉성분 또는 명확히 동일 식품 유래 원료가 전성분에 기재되면 true. RAG의 '명시된_관련원료'가 실제 전성분과 일치한다면 반드시 반영한다.
2) 1)이 아니면서 해당 알레르기와 관련된 원료의 출처가 불명확하거나, 전성분 누락·옵션 혼재로 판단할 수 없는 경우에만 null. '원료 출처 불명'은 지정 알레르기와 실제 관련성이 있을 때만 고려한다.
3) 나머지, 즉 관련 원료를 확인하지 못했고 그 알레르기를 판단하는 데 필요한 정보가 충분하면 false. 이는 안전 인증이 아니다.
중요: 전성분의 '향료'가 비공개인 점은 입력 알레르기 자체가 향료 전반 또는 리날룰 같은 특정 향료 성분인 경우에만 null 검토 사유다. 우유·계란·프로폴리스·세정 성분 등 향료와 무관한 알레르기를 '향료' 표기 때문에 null로 만들지 않는다. 일반적인 추출물·단백질·콜라겐도 지정 음식 유래로 추측하지 않는다.
성분명의 일부가 비슷해도 다른 원료를 동일시하지 않는다(유제놀/아이소유제놀, 코카미도프로필베타인/라우릴베타인). 없는 성분을 만들어내지 않는다.
모든 product_id를 한 번씩 반환한다. 설명 없이 JSON 객체만 출력하고 allergy_risk는 JSON true/false/null이다.
{"results":[{"product_id":"P001","allergy_risk":false}]}"""


def make_context(kb: AllergyKB, allergies: list[str], products: list[dict]) -> tuple[dict,dict]:
    """유사도는 오직 이미 검증된 DB 명칭 내 우선순위 정렬용. 미검증 후보는 LLM에 노출하지 않음."""
    items=[];diagnostics={}
    for allergy in allergies:
        found=kb.retrieve(allergy,products,max_examples=5,max_hits=30)
        resolution=found['resolution']
        diagnostics[allergy] = {'status':resolution['status'], 'matched':resolution['matched'],
                                'expanded':resolution['expanded'], 'unknown':resolution['unknown'],
                                'suggestions_unverified':resolution['suggestions_unverified'],
                                'knowledge_rows':found['knowledge_row_count']}
        # 상품 내 표기 확인 결과는 DB 이름-원료와 성분 토큰의 일치 결과이며 의료적으로 확정된 위험이 아님.
        item={'사용자_입력':allergy,'DB_알레르기명':resolution['matched'],
              '일치검증상태':resolution['status'],
              '상품별_원료관련성_표기': found['context']['상품별_표기확인']}
        if found['context']['관련_식품군_구성']:
            item['식품군_구성_참고']=found['context']['관련_식품군_구성']
        # 실제 제품에 없는 긴 DB 원료 예시는 전달하지 않는다.
        # 특히 여러 원료가 조합된 초장문 성분명이 판정을 혼동시키는 것을 방지.
        items.append(item)
    # 원본 전성분에 '향료'가 이미 들어있으므로 중복된 향료 상품 목록을 보내지 않는다.
    # 목록이 모든 알레르기에 무조건 제공되면 비향료 알레르기에서도 과도한 null이 발생할 수 있다.
    context={'알레르기별_검색결과':items,
             '주의':'명시된 관련 원료가 있으면 true. 관련 원료 출처 불명 등 판단불가 사유가 지정 알레르기에 직접 관계할 때만 null. 향료 비공개는 향료 관련 알레르기일 때만 고려. 미검증 임베딩 후보는 제외.'}
    return context, diagnostics


def build_request(model: str, allergies: list[str], products: list[dict], context: dict|None,
                  num_ctx: int, num_predict: int) -> dict:
    if len(products) != len({p['product_id'] for p in products}):
        raise ValueError('상품 ID 중복')
    user={
        'user_allergies': allergies,
        'products':[{'product_id':p['product_id'],'product_name':p.get('product_name',''),'ingredients':p['ingredients']}
                    for p in products],
    }
    if context is not None:user['rag_knowledge']=context
    body={'model':model,'stream':False,'format':'json',
          'messages':[{'role':'system','content':SYSTEM_PROMPT},
                      {'role':'user','content':json.dumps(user,ensure_ascii=False)}],
          'options':{'temperature':0,'num_ctx':num_ctx,'num_predict':num_predict}}
    if model.lower().startswith('qwen3'):body['think']=False
    return body
