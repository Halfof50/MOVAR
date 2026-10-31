import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { useAccount, errorMessage } from '../account/AccountContext'
import { getCareSummary } from '../services/careSummary'
import { api } from '../services/api'
import type { StoredAnalysis } from '../services/api'
export default function CarePage() {
  const { user, records, historyError, refresh } = useAccount()
  const summary = getCareSummary(records)
  const latestId = summary?.latest.id
  const [detail, setDetail] = useState<{ id: string; value: StoredAnalysis | null; error: string } | null>(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!latestId) return
    let active = true
    api.getAnalysis(latestId).then(value => { if (active) setDetail({ id: latestId, value, error: '' }) })
      .catch(error => { if (active) setDetail({ id: latestId, value: null, error: errorMessage(error) }) })
    return () => { active = false }
  }, [latestId, attempt])
  if (!user) return <section className="card narrow"><h1>맞춤 케어</h1><p>로그인 후 저장한 분석 기록을 바탕으로 케어 내용을 확인할 수 있어요.</p><Link className="button" to="/login">로그인하기</Link></section>
  if (historyError) return <section className="card"><h1>맞춤 케어</h1><p role="alert">{historyError}</p><button className="button" onClick={()=>void refresh()}>다시 불러오기</button></section>
  if (!summary) return <section className="card narrow"><h1>첫 기록부터 시작해요</h1><p>맞춤 케어를 표시하려면 저장된 분석이 필요해요.</p><Link className="button" to="/capture">두피 촬영하기</Link></section>
  const current = detail?.id === latestId ? detail : null
  const report = current?.value?.report
  return <div className="stack account-page"><section className="page-heading"><p className="eyebrow">MY CARE</p><h1>기록으로 살펴보는 나의 케어</h1><p>최근 {summary.count}건의 분석 기록과 가장 최근 리포트를 바탕으로 구성했어요.</p></section>
    <section className="card"><h2>다음 기록에서 살펴볼 항목</h2><div className="care-priorities">{summary.priorities.map(item=><article key={item.id}><h3>{item.name}</h3><strong>평균 {item.average.toFixed(1)}단계</strong><p>다음 촬영 시 같은 부위를 기록해 변화를 비교해보세요.</p></article>)}</div></section>
    {!current ? <section className="card" role="status">최근 리포트를 불러오는 중이에요…</section>
      : !report ? <section className="card"><p role="alert">{current.error}</p><button className="button" onClick={() => { setDetail(null); setAttempt(n => n + 1) }}>다시 불러오기</button></section>
      : <>
        <section className="card"><h2>{report.headline}</h2><p>{report.summary}</p></section>
        <section className="card"><h2>맞춤 케어 가이드</h2><ol className="report-guides">{report.care_guides.map(guide => <li key={guide.title}><strong>{guide.title}</strong><p>{guide.description}</p></li>)}</ol></section>
        <section className="card"><h2>추천 관리 루틴</h2><div className="report-routine"><div><h3>오전</h3><ul>{report.routine.morning.map(step => <li key={step}>{step}</li>)}</ul></div><div><h3>오후</h3><ul>{report.routine.evening.map(step => <li key={step}>{step}</li>)}</ul></div></div>
          <p className="account-small">{report.disclaimer} 위 안내는 의료적 판단이나 치료 안내가 아니에요.</p></section>
      </>}
    <div className="account-actions"><Link className="button" to={`/history/${summary.latest.id}`}>최근 결과 보기</Link><Link className="button account-secondary" to="/mypage">분석 기록 보기</Link></div>
  </div>
}
