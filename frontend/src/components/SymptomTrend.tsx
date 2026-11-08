import { useState } from 'react'
import { demoScalpResults, severityLabels } from '../data/scalpResults'
import { sampleTrendRecords } from '../data/symptomTrend'
import type { TrendRecord } from '../data/symptomTrend'
import './SymptomTrend.css'

const colors = ['#287abe', '#9a6100', '#c74568', '#7755b5', '#18816d', '#596675']
const dateLabel = (date: string) => date.slice(5).replace('-', '.')
export default function SymptomTrend({ records = sampleTrendRecords }: { records?: TrendRecord[] }) {
  const [selected, setSelected] = useState(demoScalpResults.map(item => item.id))
  const [activeDate, setActiveDate] = useState<string | null>(null)
  const sorted = [...records].sort((a, b) => a.date.localeCompare(b.date))
  const current = sorted.find(row => row.date === activeDate) ?? sorted.at(-1)
  const visible = demoScalpResults.filter(item => selected.includes(item.id))
  const all = selected.length === demoScalpResults.length
  const x = (index: number) => sorted.length === 1 ? 420 : 90 + index * 660 / (sorted.length - 1)
  const y = (level: number) => 220 - level * 60
  function toggle(id: string) {
    setSelected(previous => previous.includes(id) ? previous.filter(value => value !== id) : [...previous, id])
  }
  return <section className="card symptom-trend" aria-labelledby="trend-title">
    <div className="trend-heading"><div><p className="eyebrow">SCALP HISTORY</p><h2 id="trend-title">증상 변화 그래프</h2></div><span className="badge">샘플 데이터</span></div>
    <p>관심 있는 증상을 선택해 날짜별 변화를 비교해보세요. 여러 증상을 함께 볼 수 있어요.</p>
    <p className="trend-disclaimer">기능 체험을 위한 가상 기록이며 실제 분석 기록과 관계없어요. 샘플은 계정에 저장되지 않아요.</p>
    <div className="trend-filters" role="group" aria-label="표시할 증상 선택">
      <button type="button" aria-pressed={all} onClick={() => setSelected(demoScalpResults.map(item => item.id))}>전체 보기</button>
      {demoScalpResults.map((item, index) => <button type="button" key={item.id} aria-pressed={selected.includes(item.id)} onClick={() => toggle(item.id)}><span style={{ background: colors[index] }} aria-hidden="true" />{item.name}</button>)}
    </div>
    {!sorted.length ? <p role="status">표시할 기록이 없어요.</p> : !visible.length ? <p className="trend-empty" role="status">그래프에 표시할 증상을 선택해주세요.</p> : <>
      <p className="trend-direction">단계가 낮을수록 증상 정도가 낮아요 · 선이 겹칠 때는 증상을 개별 선택해보세요.</p>
      <div className="trend-scroll" tabIndex={0} role="region" aria-label="증상 변화 그래프, 좁은 화면에서는 좌우로 스크롤할 수 있어요">
        <svg viewBox="0 0 800 270" className="trend-svg" role="img" aria-label={`${visible.map(item => item.name).join(', ')}의 날짜별 0~3단계 변화. 아래에서 날짜별 수치를 확인할 수 있습니다.`}>
          {[0, 1, 2, 3].map(level => <g key={level}><line x1="90" x2="750" y1={y(level)} y2={y(level)} stroke="#dce5ee" /><text x="78" y={y(level) + 5} textAnchor="end">{level} {severityLabels[level]}</text></g>)}
          {sorted.map((row, index) => <text key={row.date} x={x(index)} y="249" textAnchor="middle">{dateLabel(row.date)}</text>)}
          {visible.map(item => {
            const color = colors[demoScalpResults.findIndex(symptom => symptom.id === item.id)]
            return <g key={item.id}><polyline fill="none" stroke={color} strokeWidth="2.5" points={sorted.map((row, index) => `${x(index)},${y(row.symptoms[item.id])}`).join(' ')} />{sorted.map((row, index) => <circle key={row.date} cx={x(index)} cy={y(row.symptoms[item.id])} r="4" fill="white" stroke={color} strokeWidth="2"><title>{row.date} {item.name}: {row.symptoms[item.id]}단계</title></circle>)}</g>
          })}
        </svg>
      </div>
      <div className="trend-detail"><label>날짜별 결과 <select value={current?.date ?? ''} onChange={event => setActiveDate(event.target.value)}>{sorted.map(row => <option key={row.date} value={row.date}>{row.date}</option>)}</select></label>
        {current && <ul>{visible.map(item => <li key={item.id}><span style={{ background: colors[demoScalpResults.findIndex(symptom => symptom.id === item.id)] }} aria-hidden="true" /><span>{item.name}</span><strong>{current.symptoms[item.id]}단계 · {severityLabels[current.symptoms[item.id]]}</strong></li>)}</ul>}
      </div>
      <details className="trend-table"><summary>전체 날짜의 수치 보기</summary><div className="trend-scroll" tabIndex={0}><table><caption>샘플 증상 기록 (0 정상 · 1 경증 · 2 중등도 · 3 중증)</caption><thead><tr><th scope="col">날짜</th>{visible.map(item => <th key={item.id} scope="col">{item.name}</th>)}</tr></thead><tbody>{sorted.map(row => <tr key={row.date}><th scope="row">{row.date}</th>{visible.map(item => <td key={item.id}>{row.symptoms[item.id]}</td>)}</tr>)}</tbody></table></div></details>
    </>}
  </section>
}
