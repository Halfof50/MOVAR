import { demoScalpResults } from './scalpResults'
import { SYMPTOM_KEY } from '../services/api'
import type { AnalysisResult } from '../services/api'

export const sampleAnalysis: AnalysisResult = {
  analysis_id: null,
  symptoms: Object.fromEntries(demoScalpResults.map(item => [SYMPTOM_KEY[item.id], item.level])),
  recommendations: [],
  report: {
    analyzed_at: '2026-11-08T12:00:00+09:00', care_score: null,
    headline: '유분 밸런스를 살펴보세요',
    headline_text: '화면 확인을 위해 준비한 샘플 리포트예요.',
    summary: '실제 사진을 분석한 결과가 아니에요. 항목별 단계와 케어 가이드의 표시 상태를 확인할 수 있어요.',
    conditions: demoScalpResults.map(item => ({ code: SYMPTOM_KEY[item.id], label: item.name, level: item.level, description: item.details[item.level] })),
    care_guides: [
      { title: '부드럽게 세정하기', description: '손끝으로 가볍게 마사지하며 충분히 헹궈주세요.' },
      { title: '두피까지 말리기', description: '뜨겁지 않은 바람으로 두피를 말려주세요.' },
      { title: '변화 살펴보기', description: '같은 조명에서 두피 상태를 비교해보세요.' },
    ],
    routine: { morning: ['두피 상태 확인하기'], evening: ['부드럽게 세정하고 충분히 말리기'] },
    products: [], disclaimer: 'UI 확인용 샘플이며 실제 분석·의료 진단이 아닙니다.',
  },
}
