import { demoScalpResults } from '../data/scalpResults'
import type { AnalysisRecord } from './accountApi'
// Display-only demo rule. Replace with the future care API, including questionnaire inputs.
export function getCareSummary(records: AnalysisRecord[]) {
  const recent = [...records].sort((a,b) => b.createdAt.localeCompare(a.createdAt)).slice(0,3)
  if (!recent.length) return null
  const priorities = demoScalpResults.map(item => ({
    id: item.id, name: item.name,
    average: recent.reduce((sum,r) => sum + (r.scores.find(s => s.id === item.id)?.level ?? 0),0) / recent.length,
  })).sort((a,b) => b.average - a.average).slice(0,2)
  return { count: recent.length, priorities, latest: recent[0] }
}
