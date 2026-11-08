import type { Severity } from '../data/scalpResults'

export type TrendRecord = { date: string; symptoms: Record<string, Severity> }
// Demonstration data only. Replace this array with mapped analysis history later.
export const sampleTrendRecords: TrendRecord[] = [
  { date: '2026-09-27', symptoms: { flakes: 3, sebum: 3, redness: 2, pustules: 2, dandruff: 3, hairloss: 2 } },
  { date: '2026-10-04', symptoms: { flakes: 2, sebum: 3, redness: 2, pustules: 1, dandruff: 2, hairloss: 2 } },
  { date: '2026-10-11', symptoms: { flakes: 2, sebum: 2, redness: 3, pustules: 1, dandruff: 2, hairloss: 2 } },
  { date: '2026-10-18', symptoms: { flakes: 1, sebum: 2, redness: 2, pustules: 0, dandruff: 1, hairloss: 2 } },
  { date: '2026-10-25', symptoms: { flakes: 2, sebum: 1, redness: 1, pustules: 1, dandruff: 2, hairloss: 1 } },
  { date: '2026-11-01', symptoms: { flakes: 1, sebum: 2, redness: 1, pustules: 0, dandruff: 1, hairloss: 1 } },
  { date: '2026-11-08', symptoms: { flakes: 1, sebum: 1, redness: 0, pustules: 0, dandruff: 1, hairloss: 1 } },
]
