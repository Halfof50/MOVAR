import { useEffect, useRef, useState } from 'react'
import { errorMessage } from '../account/AccountContext'
import type { AnalysisResult } from '../services/api'
import './AnalysisLoading.css'

type Props = {
  imageUrl: string
  run: (signal: AbortSignal) => Promise<AnalysisResult>
  onCancel: () => void
  onComplete: (result: AnalysisResult) => void
}

// The whole analysis (photo -> symptoms -> products -> report) takes about 20 seconds, so the bar eases toward 95%.
const progressAt = (seconds: number) => Math.min(95, Math.round(100 * (1 - Math.exp(-seconds / 12))))
const statusAt = (seconds: number) => seconds < 2 ? '사진 보내는 중' : seconds < 5 ? '두피를 살펴보는 중' : seconds < 18 ? '맞는 제품을 찾는 중' : '리포트를 작성하는 중'

export default function AnalysisLoading({ imageUrl, run, onCancel, onComplete }: Props) {
  const [seconds, setSeconds] = useState(0)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const heading = useRef<HTMLHeadingElement>(null)
  const controller = useRef<AbortController | null>(null)
  const started = useRef(-1)
  const alive = useRef(true)
  const latest = useRef({ run, onComplete })
  useEffect(() => { latest.current = { run, onComplete } })
  useEffect(() => { heading.current?.focus() }, [])
  useEffect(() => {
    alive.current = true
    // React StrictMode runs effects twice in development; only one request may be sent per attempt.
    if (started.current !== attempt) {
      started.current = attempt
      const request = new AbortController()
      controller.current = request
      latest.current.run(request.signal).then(result => {
        if (alive.current && !request.signal.aborted) latest.current.onComplete(result)
      }).catch(cause => {
        if (alive.current && !request.signal.aborted) setError(errorMessage(cause))
      })
    }
    const start = performance.now()
    const timer = window.setInterval(() => setSeconds((performance.now() - start) / 1000), 250)
    return () => { alive.current = false; window.clearInterval(timer) }
  }, [attempt])

  function cancel() { controller.current?.abort(); onCancel() }
  function retry() { setError(''); setSeconds(0); setAttempt(n => n + 1) }

  const progress = progressAt(seconds)
  return (
    <section className="analysis-loading" aria-labelledby="analysis-heading">
      <p className="analysis-eyebrow">MOVAR · AI ANALYSIS</p>
      <h1 id="analysis-heading" ref={heading} tabIndex={-1}>{error ? '분석을 마치지 못했어요' : '두피 상태를 살펴보는 중'}</h1>
      <p className="analysis-intro">{error ? '잠시 후 다시 시도하거나 다른 사진으로 분석해주세요.' : '20초 안팎이 걸려요. 잠시만 기다려주세요'}</p>
      <div className="analysis-lens">
        <div className="analysis-photo">
          <img src={imageUrl} alt="분석을 위해 촬영하거나 선택한 두피 사진" />
          {!error && <><div className="analysis-grid" aria-hidden="true" /><div className="analysis-laser" aria-hidden="true" /></>}
        </div>
      </div>
      {error ? <div className="capture-error" role="alert">{error}</div> : (
        <div className="analysis-progress">
          <div className="analysis-status"><strong role="status">{statusAt(seconds)}</strong><span aria-hidden="true">{progress}%</span></div>
          <div className="analysis-track" role="progressbar" aria-label="분석 진행률" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
            <div style={{ width: `${progress}%` }} />
          </div>
        </div>
      )}
      <p className="analysis-disclaimer">AI 분석 결과는 참고용이며 의료진의 진단을 대체하지 않아요.</p>
      {error && <button className="button analysis-cancel" onClick={retry}>다시 시도</button>}
      <button className="button capture-secondary analysis-cancel" onClick={cancel}>{error ? '돌아가기' : '×   분석 취소'}</button>
    </section>
  )
}
