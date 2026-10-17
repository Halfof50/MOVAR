import { demoScalpResults } from '../data/scalpResults'
import type { Severity } from '../data/scalpResults'

export type User = { id: string; name: string; email: string }
export type AnalysisRecord = {
  id: string; userId: string; createdAt: string; photoName: string
  source: 'demo'; sample: boolean; scores: { id: string; level: Severity }[]
}
export const DEMO_EMAIL = 'demo@movar.test'
export const DEMO_PASSWORD = 'movar1234'
const demoUser: User = { id: 'movar-demo-user', name: '테스트 사용자', email: DEMO_EMAIL }
const sessionKey = 'movar.demo.session.v1'
const historyKey = (id: string) => `movar.demo.history.v1.${id}`

function requireSession(userId: string) {
  if (sessionStorage.getItem(sessionKey) !== userId || userId !== demoUser.id) {
    throw new Error('로그인이 필요해요. 다시 로그인해주세요.')
  }
}
function readRecords(userId: string): AnalysisRecord[] {
  const raw = localStorage.getItem(historyKey(userId))
  if (!raw) return []
  const records: AnalysisRecord[] = JSON.parse(raw)
  if (!Array.isArray(records) || records.some(r => !r || r.userId !== userId ||
    typeof r.id !== 'string' || typeof r.photoName !== 'string' || r.source !== 'demo' ||
    !Number.isFinite(Date.parse(r.createdAt)) || !Array.isArray(r.scores) ||
    r.scores.length !== demoScalpResults.length ||
    demoScalpResults.some(item => r.scores.filter(s => s?.id === item.id && Number.isInteger(s.level) && s.level >= 0 && s.level <= 3).length !== 1))) {
    throw new Error('저장된 기록을 읽을 수 없어요. 브라우저 저장 데이터를 확인해주세요.')
  }
  return records.sort((a, b) => b.createdAt.localeCompare(a.createdAt))
}
export function createDemoRecord(userId: string, photoName: string): AnalysisRecord {
  return { id: crypto.randomUUID(), userId, createdAt: new Date().toISOString(), photoName,
    source: 'demo', sample: false, scores: demoScalpResults.map(({ id, level }) => ({ id, level })) }
}

// Demo adapter only. Replace these methods with server authentication and DB APIs.
// The browser demo password is public; it is not a production security boundary.
// Production must derive the account from a server session, not trust userId input.
export const accountApi = {
  async getSession(): Promise<User | null> {
    return sessionStorage.getItem(sessionKey) === demoUser.id ? demoUser : null
  },
  async login(email: string, password: string): Promise<User> {
    if (email.trim().toLowerCase() !== DEMO_EMAIL || password !== DEMO_PASSWORD) throw new Error('이메일 또는 비밀번호가 올바르지 않아요.')
    sessionStorage.setItem(sessionKey, demoUser.id)
    return demoUser
  },
  async logout(): Promise<void> { sessionStorage.removeItem(sessionKey) },
  async listAnalyses(userId: string): Promise<AnalysisRecord[]> {
    requireSession(userId)
    return readRecords(userId)
  },
  async saveAnalysis(userId: string, record: AnalysisRecord): Promise<void> {
    requireSession(userId)
    if (record.userId !== userId) throw new Error('계정이 일치하지 않아요.')
    const records = readRecords(userId)
    if (records.some(r => r.id === record.id)) return
    try { localStorage.setItem(historyKey(userId), JSON.stringify([record, ...records])) }
    catch { throw new Error('기록을 저장하지 못했어요. 브라우저 저장 공간과 설정을 확인한 뒤 다시 시도해주세요.') }
  },
  async addSamples(userId: string): Promise<void> {
    requireSession(userId)
    for (let i = 1; i <= 3; i++) {
      const record = createDemoRecord(userId, `체험용 기록 ${i}`)
      record.id = `sample-${i}`
      record.sample = true
      record.createdAt = new Date(Date.now() - i * 86400000).toISOString()
      record.scores = record.scores.map(s => ({ ...s, level: ((s.level + i) % 3) as Severity }))
      await this.saveAnalysis(userId, record)
    }
  },
}
