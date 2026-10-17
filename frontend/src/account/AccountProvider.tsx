import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { accountApi } from '../services/accountApi'
import type { AnalysisRecord, User } from '../services/accountApi'
import { AccountContext, errorMessage } from './AccountContext'

export default function AccountProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)
  const [records, setRecords] = useState<AnalysisRecord[]>([])
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
    accountApi.getSession().then(async session => {
      if (!active) return
      activeId.current = session?.id ?? null
      setUser(session)
      if (session) await load(session.id)
    }).catch(error => { if (active) setHistoryError(errorMessage(error)) })
      .finally(() => { if (active) setReady(true) })
    return () => { active = false; activeId.current = null }
  }, [])
  async function login(email: string, password: string) {
    const session = await accountApi.login(email, password)
    activeId.current = session.id
    setUser(session); setRecords([]); setHistoryError('')
    await load(session.id)
  }
  async function logout() {
    await accountApi.logout()
    activeId.current = null
    setUser(null); setRecords([]); setHistoryError('')
  }
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
  return <AccountContext.Provider value={{ user, ready, records, historyError, login, logout, refresh, save, addSamples }}>{children}</AccountContext.Provider>
}
