import { Link } from 'react-router'

const steps = [
  { title: '두피 촬영', text: '두피 사진을 촬영하거나 선택해요.' },
  { title: 'AI 분석', text: '촬영한 이미지를 분석해요.' },
  { title: '간단 문진', text: '생활 습관과 고민을 알려주세요.' },
  { title: '맞춤 추천', text: '나에게 맞는 케어를 확인해요.' },
]

export default function HomePage() {
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
          <div className="status-overview">
            <div className="score-ring" aria-label="케어 지수 없음">
              <strong>—</strong>
              <span>케어 지수</span>
            </div>
            <div>
              <h3>아직 분석 기록이 없어요</h3>
              <p>두피 사진을 분석하면<br />이곳에서 상태를 확인할 수 있어요.</p>
            </div>
          </div>
          <div className="status-metrics">
            {['유분', '각질', '붉은기'].map((name) => (
              <div key={name}>
                <span>{name}</span>
                <strong>분석 전</strong>
                <div className="metric-track" />
              </div>
            ))}
          </div>
          <Link className="result-link" to="/results">결과 보기 →</Link>
        </section>

        <section className="card product-card">
          <h2>헤어케어 상품 추천</h2>
          <div className="product-empty">준비 중</div>
        </section>

        <section className="card care-card">
          <div>
            <p className="eyebrow">MOVAR AI 에이전트</p>
            <h2>분석에서 케어까지, 함께.</h2>
            <p>나의 고민과 생활 습관을 반영한<br />맞춤 케어를 준비하고 있어요.</p>
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