import type { AnalysisRecord } from '../services/accountApi'
import { Link } from 'react-router'
import type { AnalysisPhoto } from '../data/scalpResults'
import { demoScalpResults, severityLabels } from '../data/scalpResults'
import './ResultsPage.css'

export default function ResultsPage({ photo, record }: { photo: AnalysisPhoto | null; record?: AnalysisRecord }) {
  const results = record ? demoScalpResults.map(item => ({ ...item, level: record.scores.find(s => s.id === item.id)?.level ?? item.level })) : demoScalpResults
  if (!photo && !record) return (
    <section className="card results-empty">
      <p className="eyebrow">SCALP REPORT</p><h1>아직 분석한 사진이 없어요</h1>
      <p>사진을 촬영하거나 업로드하면 예시 결과 화면을 확인할 수 있어요.<br />로그인 후 저장한 결과는 마이페이지에서 다시 확인할 수 있어요.</p>
      <Link className="button" to="/capture">사진 촬영·선택하기</Link>
    </section>
  )
  return (
    <div className="stack results-page">
      <section className="page-heading results-heading">
        <div><p className="eyebrow">SCALP REPORT</p><h1>두피 분석 결과</h1><p>6가지 항목을 0~3단계로 살펴보세요.</p></div>
        <span className="badge">예시 결과 · DEMO</span>
      </section>
      {record && <p className="record-analysis-date"><time dateTime={record.createdAt}>{new Date(record.createdAt).toLocaleString('ko-KR')}</time> · {record.sample ? '체험용 샘플' : '분석 데모'}</p>}
      <div className="results-demo" role="note"><strong>실제 사진 분석 결과가 아닙니다.</strong> 실제 사진을 판독하지 않는 데모입니다. 새 사진 분석은 고정 예시 값이며 체험용 기록은 별도로 구성한 샘플이에요.</div>
      <section className="card results-overview" aria-label="선택한 사진과 결과 요약">
        {photo ? <figure className="results-photo"><img src={photo.url} alt="촬영하거나 업로드한 원본 사진" /><figcaption title={photo.name}>{photo.name}</figcaption></figure> : <div className="record-photo-placeholder"><div><strong>{record?.photoName}</strong><p>원본 사진은 저장하지 않았어요.</p><span className="badge">데모 기록</span></div></div>}
        <div className="results-summary"><p className="eyebrow">한눈에 보는 예시 결과</p><h2>항목별 상태를 확인해보세요</h2><p>아래에서 각 항목의 단계와 기준을 확인할 수 있어요.</p>
          <div className="results-counts">{severityLabels.map((label, level) => <div key={label} className={`severity-${level}`}><span>{label}</span><strong>{results.filter(item => item.level === level).length}<small>개</small></strong></div>)}</div>
          <p className="results-small">0 정상 · 1 경증 · 2 중등도 · 3 중증</p>
        </div>
      </section>
      <section aria-labelledby="results-detail-title"><div className="results-section-title"><h2 id="results-detail-title">항목별 상세 결과</h2><span>예시 데이터</span></div>
        <div className="results-grid">{results.map((item, index) => <article className="card result-item" key={item.id}>
          <div className="result-item-title"><div><span className="result-index">0{index + 1}</span><h3>{item.name}</h3></div><span className={`result-level severity-${item.level}`}>{item.level}단계 · {severityLabels[item.level]}</span></div>
          <p className="result-description">{item.description}</p>
          <div className="result-scale" aria-label={`${item.name}: 예시 ${item.level}단계 ${severityLabels[item.level]}`}>{severityLabels.map((label, level) => <div key={label} className={level === item.level ? `selected severity-${level}` : ''}><span>{level === item.level ? '● ' : ''}{level}</span><small>{label}</small></div>)}</div>
          <p className="result-explanation"><strong>{item.stages[item.level]}</strong><span>{item.details[item.level]}</span></p>
        </article>)}</div>
      </section>
      <details className="card results-reference"><summary>0~3단계 전체 기준 보기</summary><div className="results-table-wrap" tabIndex={0} role="region" aria-label="항목별 전체 단계 기준 표"><table><caption>제공 자료를 바탕으로 정리한 화면 표시 기준</caption><thead><tr><th scope="col">항목</th>{severityLabels.map((label, level) => <th scope="col" key={label}>{level} · {label}</th>)}</tr></thead><tbody>{results.map(item => <tr key={item.id}><th scope="row">{item.name}</th>{item.stages.map((stage, level) => <td key={level}>{stage}<small>{item.details[level]}</small></td>)}</tr>)}</tbody></table></div></details>
      <section className="notice results-notice"><strong>두피 상태를 이해하기 위한 참고 화면이에요.</strong><p>표시된 단계는 의료적 진단이 아닙니다. 현재 예시 데이터로는 실제 두피 상태를 판단할 수 없어요.</p></section>
      <div className="results-actions"><Link className="button" to="/capture">다시 촬영·선택하기</Link><Link className="button capture-secondary" to="/hospitals">병원 안내 보기</Link></div>
    </div>
  )
}
