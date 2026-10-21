import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { authConfigError } from '../services/supabase'
import { accountApi } from '../services/accountApi'
import type { AnalysisRecord, User } from '../services/accountApi'
import { AccountContext, errorMessage } from './AccountContext'

export default function AccountProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)
  const [records, setRecords] = useState<AnalysisRecord[]>([])
  const [authError, setAuthError] = useState(authConfigError)
  const [historyError, setHistoryError] = useState('')
  const activeId = useRef<string | null>(null)
  async function load(id: string) {
    try {
      const rows = await accountApi.listAnalyses(id)
      if (activeId.current === id) { setRecords(rows); setHistoryError('') }
    } catch (error) {
      if (activeId.current === id) setHistoryError(errorMessage(error))
    }
  }
  useEffect(() => {
    let active = true
    let revision = 0
    function apply(session: User | null) {
      if (!active) return
      const changedAccount = activeId.current !== (session?.id ?? null)
      activeId.current = session?.id ?? null
      setUser(session)
      if (changedAccount) { setRecords([]); setHistoryError('') }
      setAuthError('')
      setReady(true)
    }
    // Keep callback synchronous: do not call other Auth methods inside its lock.
    const unsubscribe = accountApi.subscribe(session => {
      revision++
      apply(session)
    })
    const initialRevision = revision
    accountApi.getSession().then(session => {
      if (revision === initialRevision) apply(session)
    }).catch(error => {
      if (active && revision === initialRevision) {
        setAuthError(errorMessage(error)); setReady(true)
      }
    })
    return () => { active = false; activeId.current = null; unsubscribe() }
  }, [])
  useEffect(() => {
    let active = true
    if (user) {
      accountApi.listAnalyses(user.id).then(rows => {
        if (active) { setRecords(rows); setHistoryError('') }
      }).catch(error => { if (active) setHistoryError(errorMessage(error)) })
    }
    return () => { active = false }
  }, [user])
  async function login(email: string, password: string) {
    await accountApi.login(email, password)
    // Auth event updates all consumers, including other tabs.
  }
  async function updateNickname(nickname: string) {
    if (!user) throw new Error('로그인이 필요해요.')
    const updated = await accountApi.updateNickname(nickname)
    if (activeId.current === updated.id) setUser(updated)
  }
  async function logout() { await accountApi.logout() }
  async function refresh() { if (user) await load(user.id) }
  async function save(record: AnalysisRecord) {
    if (!user) throw new Error('로그인이 필요해요.')
    await accountApi.saveAnalysis(user.id, record)
    await load(user.id)
  }
  async function addSamples() {
    if (!user) throw new Error('로그인이 필요해요.')
    await accountApi.addSamples(user.id)
    await load(user.id)
  }
  return <AccountContext.Provider value={{ user, ready, records, historyError, authError, login, updateNickname, logout, refresh, save, addSamples }}>{children}</AccountContext.Provider>
}
