export const severityLabels = ['정상', '경증', '중등도', '중증'] as const
export type Severity = 0 | 1 | 2 | 3
export type AnalysisPhoto = { url: string; name: string }

// UI demonstration only: never inferred from the submitted image.
export const demoScalpResults: { id: string; name: string; description: string; level: Severity; stages: string[]; details: string[] }[] = [
  { id: 'flakes', name: '미세각질', description: '두피 표면의 작은 각질 정도', level: 1, stages: ['거의 없음', '약간 있음', '뚜렷하게 있음', '매우 많음'], details: ['정상 범위', '경미한 각질', '눈에 띄는 각질', '심한 각질·비듬'] },
  { id: 'sebum', name: '피지과다', description: '두피의 유분 분비 정도', level: 2, stages: ['정상', '약간 많음', '많음', '매우 많음'], details: ['유분 밸런스 유지', '가벼운 유분감', '번들거림·끈적임', '과도한 유분·떡짐'] },
  { id: 'redness', name: '모낭사이홍반', description: '모낭 사이 두피의 붉은 정도', level: 1, stages: ['없음', '약간 있음', '뚜렷함', '심함'], details: ['정상', '가벼운 홍반', '눈에 띄는 홍반', '광범위한 홍반'] },
  { id: 'pustules', name: '모낭홍반농포', description: '모낭 주변 홍반·농포 정도', level: 0, stages: ['없음', '약간 있음', '뚜렷함', '심함'], details: ['정상', '소수의 홍반', '다수의 홍반', '광범위한 홍반·농포'] },
  { id: 'dandruff', name: '비듬', description: '두피에 보이는 비듬의 정도', level: 1, stages: ['거의 없음', '약간 있음', '많음', '매우 많음'], details: ['정상', '소량의 비듬', '눈에 띄는 비듬', '광범위한 비듬'] },
  { id: 'hairloss', name: '탈모', description: '모발 밀도 감소 정도', level: 0, stages: ['정상', '약간 감소', '뚜렷한 감소', '심한 감소'], details: ['모발 밀도 양호', '밀도 저하 시작', '눈에 띄는 탈모', '광범위한 탈모'] },
]
