import { isLocalAuth } from './authMode'
import { localAuth } from './localAuth'
import type { User as SupabaseUser } from '@supabase/supabase-js'
import { supabase, getSupabase, authErrorMessage } from './supabase'
import { api, SYMPTOM_KEY } from './api'
import type { HistoryItem } from './api'
import { demoScalpResults } from '../data/scalpResults'
import type { Severity } from '../data/scalpResults'

export type User = { id: string; name: string; email: string }
export type AnalysisRecord = {
  id: string; userId: string; createdAt: string; title: string
  sample: boolean; scores: { id: string; level: Severity }[]
}
export function toAccountUser(user: SupabaseUser): User {
  const name = [user.user_metadata?.display_name, user.user_metadata?.full_name, user.user_metadata?.name]
    .find(value => typeof value === 'string' && value.trim())
  return { id: user.id, email: user.email ?? '',
    name: typeof name === 'string' && name.trim() ? name.trim() : user.email?.split('@')[0] || '사용자' }
}

// Analyses live on the backend. In local demo mode the backend sees every user as a guest
// (guests share one list), so each browser remembers which analysis ids belong to which account.
type Owned = { id: number; sample: boolean }
const ownedKey = (id: string) => `movar.analyses.v1.${id}`
function readOwned(userId: string): Owned[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(ownedKey(userId)) ?? '[]')
    return Array.isArray(value) ? value.filter((item): item is Owned => !!item && Number.isInteger(item.id)) : []
  } catch { return [] }
}
function remember(userId: string, id: number, sample: boolean) {
  const owned = readOwned(userId)
  if (owned.some(item => item.id === id)) return
  try { localStorage.setItem(ownedKey(userId), JSON.stringify([{ id, sample }, ...owned].slice(0, 50))) }
  catch { /* the list is only a filter; the analysis itself is already saved */ }
}
function toRecord(userId: string, item: HistoryItem, sample: boolean): AnalysisRecord {
  return {
    id: String(item.analysis_id), userId, createdAt: item.analyzed_at, title: item.headline, sample,
    scores: demoScalpResults.map(({ id }) => ({ id, level: Math.min(3, Math.max(0, item.symptoms[SYMPTOM_KEY[id]] ?? 0)) as Severity })),
  }
}
async function requireSession(userId: string) {
  const user = await accountApi.getSession()
  if (!user || user.id !== userId)
    throw new Error('로그인이 필요해요. 다시 로그인해주세요.')
}

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
    const { items } = await api.listAnalyses(50)
    const owned = readOwned(userId)
    const visible = isLocalAuth ? items.filter(item => owned.some(o => o.id === item.analysis_id)) : items
    return visible.map(item => toRecord(userId, item, owned.find(o => o.id === item.analysis_id)?.sample ?? false))
  },
  // The backend saves every finished analysis itself; this only links it to the signed-in account.
  async rememberAnalysis(userId: string, analysisId: number, sample = false): Promise<void> {
    await requireSession(userId)
    remember(userId, analysisId, sample)
  },
  async addSample(userId: string): Promise<void> {
    await requireSession(userId)
    const result = await api.mockAnalysis()
    if (result.analysis_id !== null) remember(userId, result.analysis_id, true)
  },
}
