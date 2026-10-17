import { useAccount } from '../account/AccountContext'
import { getCareSummary } from '../services/careSummary'
import { demoScalpResults, severityLabels } from '../data/scalpResults'
import ProductRecommendations from '../components/ProductRecommendations'
import { Link } from 'react-router'

const steps = [
  { title: '두피 촬영', text: '두피 사진을 촬영하거나 선택해요.' },
  { title: 'AI 분석', text: '촬영한 이미지를 분석해요.' },
  { title: '간단 문진', text: '생활 습관과 고민을 알려주세요.' },
  { title: '맞춤 추천', text: '나에게 맞는 케어를 확인해요.' },
]

export default function HomePage() {
  const { user, records, historyError } = useAccount()
  const summary = getCareSummary(records)
  const latest = records[0]
  return (
    <div className="stack">
      <section className="page-heading">
        <h1>두피를 알아가는 시간</h1>
        <p>오늘의 작은 케어가 건강한 변화를 만듭니다.</p>
      </section>

      <div className="dashboard-grid">
        <section className="capture-card">
          <div className="capture-content">
            <h2>지금, 나의 두피는<br />어떤 상태일까요?</h2>
            <p>USB 전자현미경으로 촬영하고<br />AI 분석을 시작해보세요.</p>
            <Link className="button" to="/capture">두피 촬영하기 →</Link>
          </div>
          <div className="scan-art" aria-hidden="true">
            <div className="scan-lens">◎</div>
            <span>SCALP SCAN</span>
          </div>
        </section>

        <section className="card status-card">
          <h2>최근 두피 상태</h2>
          {historyError ? <p role="alert">기록을 불러오지 못했어요. 마이페이지에서 다시 시도해주세요.</p> : latest ? <>
            <p>{new Date(latest.createdAt).toLocaleString('ko-KR')} <span className="badge">예시 결과</span></p>
            <div className="history-scores">{latest.scores.map(score => <span key={score.id} className={`severity-${score.level}`}>{demoScalpResults.find(item => item.id === score.id)?.name}<strong>{severityLabels[score.level]}</strong></span>)}</div>
            <Link className="result-link" to={`/history/${latest.id}`}>최근 결과 보기 →</Link>
          </> : <><div className="status-overview"><div><h3>아직 저장한 분석 기록이 없어요</h3><p>{user ? '사진을 분석하면 마이페이지에 기록돼요.' : '로그인하면 분석 기록을 모아볼 수 있어요.'}</p></div></div><Link className="result-link" to={user ? '/capture' : '/login'}>{user ? '분석 시작하기' : '로그인하기'} →</Link></>}

        </section>

        <ProductRecommendations />

        <section className="card care-card">
          <div>
            <p className="eyebrow">MOVAR AI 에이전트</p>
            <h2>{summary && !historyError ? `${user?.name}님의 맞춤 케어` : '기록에서 시작하는 맞춤 케어'}</h2>
            <p>{historyError ? '기록을 다시 불러온 뒤 확인해주세요.' : summary ? `최근 ${summary.count}건에서 ${summary.priorities.map(p => p.name).join(' · ')} 항목을 살펴봐요.` : user ? '첫 분석을 저장하면 케어 데모가 시작돼요.' : '로그인하고 분석 기록을 쌓아보세요.'}</p>
            {summary && <p className="account-small">예시 기록 기반 · 케어 데모</p>}
            <Link className="button" to="/care">맞춤 케어 확인하기 →</Link>
          </div>
          <div className="agent-art" aria-hidden="true">
            <div className="agent-face">⌒ ⌒</div>
            <strong>M</strong>
          </div>
        </section>
      </div>

      <section className="card usage-card">
        <h2>사용방법</h2>
        <ol className="steps">
          {steps.map((step, index) => (
            <li key={step.title}>
              <span className="step-number">0{index + 1}</span>
              <div>
                <strong>{step.title}</strong>
                <p>{step.text}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>
    </div>
  )
}