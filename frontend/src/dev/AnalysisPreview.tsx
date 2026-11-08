import { useRef, useState } from 'react'
import AnalysisLoading from '../components/AnalysisLoading'
import ResultsPage from '../pages/ResultsPage'
import { sampleAnalysis as sample } from '../data/sampleAnalysis'
import { ApiError } from '../services/api'
import type { AnalysisResult } from '../services/api'
import photo from '../assets/hero.png'


type Scenario = 'success' | 'error' | 'waiting'

export default function AnalysisPreview() {
  const [scenario, setScenario] = useState<Scenario>('success')
  const [screen, setScreen] = useState<'ready' | 'loading' | 'result'>('ready')
  const attempts = useRef(0)
  function run(signal: AbortSignal): Promise<AnalysisResult> {
    const attempt = ++attempts.current
    return new Promise((resolve, reject) => {
      const cleanup = () => { clearTimeout(timer); signal.removeEventListener('abort', abort) }
      const abort = () => { cleanup(); reject(new DOMException('Cancelled', 'AbortError')) }
      const timer = setTimeout(() => {
        cleanup()
        if (scenario === 'error' && attempt === 1) reject(new ApiError('샘플 오류', 'VISION_UNREACHABLE', 503))
        else resolve(sample)
      }, scenario === 'waiting' ? 120_000 : 1500)
      signal.addEventListener('abort', abort, { once: true })
      if (signal.aborted) abort()
    })
  }
  return <div className="stack">
    <aside className="notice" role="note"><strong>화면 확인용 샘플 모드</strong><p>실제 분석·상품 추천·리포트 API를 호출하거나 기록을 저장하지 않아요. 이미지는 화면 표시 예시예요.</p></aside>
    {screen === 'ready' && <section className="card">
      <h1>분석 화면 미리보기</h1>
      <label htmlFor="preview-scenario">확인할 동작 </label>
      <select id="preview-scenario" value={scenario} onChange={event => setScenario(event.target.value as Scenario)}>
        <option value="success">분석 대기 → 샘플 결과</option>
        <option value="error">오류 → 다시 분석 → 성공</option>
        <option value="waiting">오래 기다리기·취소 (30초 후 지연 안내)</option>
      </select>
      <p>오류 시나리오는 첫 요청만 실패하고 재시도하면 샘플 결과가 표시돼요.</p>
      <button className="button" onClick={() => { attempts.current = 0; setScreen('loading') }}>미리보기 시작</button>
    </section>}
    {screen === 'loading' && <AnalysisLoading imageUrl={photo} run={run} onCancel={() => setScreen('ready')} onComplete={() => setScreen('result')} />}
    {screen === 'result' && <><button className="button capture-secondary" onClick={() => setScreen('ready')}>다른 동작 확인하기</button><ResultsPage photo={{ url: photo, name: '화면 확인용 예시 이미지' }} result={sample} /></>}
  </div>
}
