import { isLocalAuth } from './authMode'
import { localAuth } from './localAuth'
import type { User as SupabaseUser } from '@supabase/supabase-js'
import { supabase, getSupabase, authErrorMessage } from './supabase'
import { demoScalpResults } from '../data/scalpResults'
import type { Severity } from '../data/scalpResults'

export type User = { id: string; name: string; email: string }
export type AnalysisRecord = {
  id: string; userId: string; createdAt: string; photoName: string
  source: 'demo'; sample: boolean; scores: { id: string; level: Severity }[]
}
export function toAccountUser(user: SupabaseUser): User {
  const name = [user.user_metadata?.display_name, user.user_metadata?.full_name, user.user_metadata?.name]
    .find(value => typeof value === 'string' && value.trim())
  return { id: user.id, email: user.email ?? '',
    name: typeof name === 'string' && name.trim() ? name.trim() : user.email?.split('@')[0] || '사용자' }
}
const historyKey = (id: string) => `movar.demo.history.v1.${id}`

// Local demo history only. This is not database authorization.
async function requireSession(userId: string) {
  const user = await accountApi.getSession()
  if (!user || user.id !== userId)
    throw new Error('로그인이 필요해요. 다시 로그인해주세요.')
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

// Authentication uses the selected adapter; analysis records remain local demo data.
// Future DB access must enforce auth.uid() ownership through RLS/server checks.
export const accountApi = {
  subscribe(listener: (user: User | null) => void) {
    if (isLocalAuth) return localAuth.subscribe(listener)
    const subscription = supabase?.auth.onAuthStateChange((_event, session) => {
      listener(session ? toAccountUser(session.user) : null)
    }).data.subscription
    return () => subscription?.unsubscribe()
  },
  async getSession(): Promise<User | null> {
    if (isLocalAuth) return localAuth.getSession()
    const { data, error } = await getSupabase().auth.getSession()
    if (error) throw new Error(authErrorMessage(error))
    return data.session ? toAccountUser(data.session.user) : null
  },
  async login(email: string, password: string): Promise<User> {
    if (isLocalAuth) return localAuth.login(email, password)
    const client = getSupabase()
    try {
      const { data, error } = await client.auth.signInWithPassword({ email: email.trim(), password })
      if (error) throw error
      return toAccountUser(data.user)
    } catch (error) { throw new Error(authErrorMessage(error), { cause: error }) }
  },
  async signUp(email: string, password: string, nicknameValue: string): Promise<boolean> {
    if (isLocalAuth) return localAuth.signUp(email, password, nicknameValue)
    const nickname = nicknameValue.trim()
    if (nickname.length < 2 || nickname.length > 20 || /[\p{Cc}\p{Cf}]/u.test(nickname))
      throw new Error('닉네임은 제어 문자 없이 2~20자로 입력해주세요.')
    if (password.length < 8) throw new Error('비밀번호는 8자 이상 입력해주세요.')
    const client = getSupabase()
    try {
      const { data, error } = await client.auth.signUp({
        email: email.trim(), password,
        options: {
          data: { display_name: nickname, full_name: nickname },
          emailRedirectTo: `${window.location.origin}/login`,
        },
      })
      if (error) throw error
      // A null session means email confirmation is required. Do not assume
      // a new user was created: Supabase may conceal existing accounts.
      return !!data.session
    } catch (error) { throw new Error(authErrorMessage(error), { cause: error }) }
  },
  async updateNickname(value: string): Promise<User> {
    if (isLocalAuth) return localAuth.updateNickname(value)
    const nickname = value.trim()
    if (nickname.length < 2 || nickname.length > 20)
      throw new Error('닉네임은 2~20자로 입력해주세요.')
    if (/[\p{Cc}\p{Cf}]/u.test(nickname))
      throw new Error('닉네임에 줄바꿈이나 보이지 않는 제어 문자를 사용할 수 없어요.')
    const client = getSupabase()
    const { data: sessionData, error: sessionError } = await client.auth.getSession()
    if (sessionError || !sessionData.session) throw new Error('로그인이 필요해요. 다시 로그인해주세요.')
    try {
      // Auth updates the signed-in user only and merges the metadata patch.
      // full_name mirrors the nickname for dashboard display compatibility.
      const { data, error } = await client.auth.updateUser({
        data: { display_name: nickname, full_name: nickname },
      })
      if (error) throw error
      return toAccountUser(data.user)
    } catch (error) {
      throw new Error('닉네임을 저장하지 못했어요. 로그인 상태와 인터넷 연결을 확인한 뒤 다시 시도해주세요.', { cause: error })
    }
  },
  async logout(): Promise<void> {
    if (isLocalAuth) return localAuth.logout()
    try {
      const { error } = await getSupabase().auth.signOut({ scope: 'local' })
      if (error) throw error
    } catch { throw new Error('로그아웃하지 못했어요. 연결을 확인한 뒤 다시 시도해주세요.') }
  },
  async listAnalyses(userId: string): Promise<AnalysisRecord[]> {
    await requireSession(userId)
    return readRecords(userId)
  },
  async saveAnalysis(userId: string, record: AnalysisRecord): Promise<void> {
    await requireSession(userId)
    if (record.userId !== userId) throw new Error('계정이 일치하지 않아요.')
    const records = readRecords(userId)
    if (records.some(r => r.id === record.id)) return
    try { localStorage.setItem(historyKey(userId), JSON.stringify([record, ...records])) }
    catch { throw new Error('기록을 저장하지 못했어요. 브라우저 저장 공간과 설정을 확인한 뒤 다시 시도해주세요.') }
  },
  async addSamples(userId: string): Promise<void> {
    await requireSession(userId)
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
