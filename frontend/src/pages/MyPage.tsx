import { useState } from 'react'
import { Link } from 'react-router'
import { useAccount, errorMessage } from '../account/AccountContext'
import { demoScalpResults, severityLabels } from '../data/scalpResults'

export default function MyPage() {
  const { user, records, historyError, refresh, addSamples } = useAccount()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  if (!user) return <section className="card narrow"><h1>마이페이지</h1><p>로그인하면 분석 기록과 맞춤 케어를 확인할 수 있어요.</p><Link className="button" to="/login">로그인하기</Link></section>
  async function samples() {
    setBusy(true); setError('')
    try { await addSamples() } catch(e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  return <div className="stack account-page">
    <section className="page-heading"><p className="eyebrow">MY MOVAR</p><h1>{user.name}님의 마이페이지</h1><p>{user.email}</p></section>
    <section className="card"><h2>나의 분석 기록 <span className="badge">{records.length}건</span></h2><p>최신 기록부터 표시해요. 모든 기록은 실제 AI 분석이 아닌 데모 결과입니다.</p>
      <div className="account-actions"><Link className="button" to="/capture">새 분석하기</Link><Link className="button" to="/care">맞춤 케어 보기</Link><button className="button account-secondary" onClick={samples} disabled={busy || !!historyError || records.some(r => r.sample)}>{busy ? '추가 중…' : records.some(r => r.sample) ? '체험용 기록 추가됨' : '체험용 기록 3개 추가'}</button></div>
      <p className="account-small">이 브라우저에 날짜·사진명·항목별 결과를 저장해요. 원본 사진은 저장하지 않아요.</p>
    </section>
    {error && <p role="alert" className="account-error">{error}</p>}
    {historyError ? <section className="card"><p role="alert">{historyError}</p><button className="button" onClick={()=>void refresh()}>기록 다시 불러오기</button></section> : records.length === 0 ? <section className="card"><h2>아직 저장한 분석이 없어요</h2><p>로그인 상태에서 촬영·분석하면 자동 저장돼요. 먼저 체험용 기록을 추가해 둘러볼 수도 있어요.</p></section> : <ol className="history-list">{records.map(record => <li key={record.id}><Link className="card history-card-link" to={`/history/${record.id}`} aria-label={`${new Date(record.createdAt).toLocaleString('ko-KR')} ${record.photoName} 상세 결과`}>
      <div className="history-heading"><time dateTime={record.createdAt}>{new Date(record.createdAt).toLocaleString('ko-KR')}</time><span className="badge">{record.sample ? '체험용 샘플' : '사진 분석 데모'}</span></div>
      <h2 className="history-filename">{record.photoName}</h2>
      <div className="history-scores">{record.scores.map(score => <span key={score.id} className={`severity-${score.level}`}>{demoScalpResults.find(item => item.id === score.id)?.name} <strong>{severityLabels[score.level]}</strong></span>)}</div>
    </Link></li>)}</ol>}
  </div>
}
