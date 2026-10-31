import { isLocalAuth } from '../services/authMode'
import NicknameForm from '../components/NicknameForm'
import { useState } from 'react'
import { Link } from 'react-router'
import { useAccount, errorMessage } from '../account/AccountContext'
import { demoScalpResults, severityLabels } from '../data/scalpResults'

export default function MyPage() {
  const { user, records, historyError, refresh, addSample } = useAccount()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  if (!user) return <section className="card narrow"><h1>마이페이지</h1><p>로그인하면 분석 기록과 맞춤 케어를 확인할 수 있어요.</p><Link className="button" to="/login">로그인하기</Link></section>
  async function sample() {
    setBusy(true); setError('')
    try { await addSample() } catch(e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  return <div className="stack account-page">
    <section className="page-heading"><p className="eyebrow">MY MOVAR</p><h1>{user.name}님의 마이페이지</h1><p>{user.email}</p></section>
    {isLocalAuth && <p className="notice">로컬 시연 모드 · 계정은 이 브라우저에 저장돼요. 분석 기록은 서버 메모리에 임시로 보관되어 서버를 다시 켜면 사라져요.</p>}
    <NicknameForm />
    <section className="card"><h2>나의 분석 기록 <span className="badge">{records.length}건</span></h2><p>최신 기록부터 표시해요. 새 분석을 하면 이곳에 자동으로 저장돼요.</p>
      <div className="account-actions"><Link className="button" to="/capture">새 분석하기</Link><Link className="button" to="/care">맞춤 케어 보기</Link><button className="button account-secondary" onClick={sample} disabled={busy || !!historyError}>{busy ? '추가 중… (20초 안팎)' : '체험용 기록 추가'}</button></div>
      <p className="account-small">날짜와 항목별 결과, 리포트를 저장해요. 원본 사진은 저장하지 않아요. 체험용 기록은 사진 없이 만든 샘플이라 실제 분석이 아니에요.</p>
    </section>
    {error && <p role="alert" className="account-error">{error}</p>}
    {historyError ? <section className="card"><p role="alert">{historyError}</p><button className="button" onClick={()=>void refresh()}>기록 다시 불러오기</button></section> : records.length === 0 ? <section className="card"><h2>아직 저장한 분석이 없어요</h2><p>로그인 상태에서 촬영·분석하면 자동 저장돼요. 먼저 체험용 기록을 추가해 둘러볼 수도 있어요.</p></section> : <ol className="history-list">{records.map(record => <li key={record.id}><Link className="card history-card-link" to={`/history/${record.id}`} aria-label={`${new Date(record.createdAt).toLocaleString('ko-KR')} ${record.title} 상세 결과`}>
      <div className="history-heading"><time dateTime={record.createdAt}>{new Date(record.createdAt).toLocaleString('ko-KR')}</time><span className="badge">{record.sample ? '체험용 샘플' : 'AI 분석'}</span></div>
      <h2 className="history-filename">{record.title}</h2>
      <div className="history-scores">{record.scores.map(score => <span key={score.id} className={`severity-${score.level}`}>{demoScalpResults.find(item => item.id === score.id)?.name} <strong>{severityLabels[score.level]}</strong></span>)}</div>
    </Link></li>)}</ol>}
  </div>
}
