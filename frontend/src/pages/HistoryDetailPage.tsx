import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { useAccount, errorMessage } from '../account/AccountContext'
import { api } from '../services/api'
import type { StoredAnalysis } from '../services/api'
import ResultsPage from './ResultsPage'
export default function HistoryDetailPage() {
  const { id } = useParams()
  const { user, records, historyError, refresh } = useAccount()
  const record = user ? records.find(r => r.id === id && r.userId === user.id) : undefined
  const [detail, setDetail] = useState<{ id: string; value: StoredAnalysis | null; error: string } | null>(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!record) return
    let active = true
    api.getAnalysis(record.id).then(value => { if (active) setDetail({ id: record.id, value, error: '' }) })
      .catch(error => { if (active) setDetail({ id: record.id, value: null, error: errorMessage(error) }) })
    return () => { active = false }
  }, [record?.id, attempt]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!user) return <section className="card"><h1>로그인이 필요해요</h1><Link className="button" to="/login">로그인</Link></section>
  if (historyError) return <section className="card"><p role="alert">{historyError}</p><button className="button" onClick={()=>void refresh()}>다시 불러오기</button></section>
  if (!record) return <section className="card"><h1>기록을 찾을 수 없어요</h1><Link to="/mypage">마이페이지로 돌아가기</Link></section>
  const current = detail?.id === record.id ? detail : null
  if (!current) return <section className="card" role="status">분석 기록을 불러오는 중이에요…</section>
  if (!current.value) return <section className="card"><p role="alert">{current.error}</p><button className="button" onClick={() => { setDetail(null); setAttempt(n => n + 1) }}>다시 불러오기</button></section>
  return <div className="stack"><Link className="text-link" to="/mypage">← 전체 기록</Link><ResultsPage photo={null} result={current.value} createdAt={record.createdAt} /></div>
}
