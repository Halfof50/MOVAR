import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../services/api'
import { ANALYSIS_DELAY_MS, startAnalysisAttempt } from '../services/analysisAttempt'
import type { AnalysisResult } from '../services/api'
import './AnalysisLoading.css'

type Props = {
  imageUrl: string
  run: (signal: AbortSignal) => Promise<AnalysisResult>
  onCancel: () => void
  onComplete: (result: AnalysisResult) => void
}

function analysisError(cause: unknown) {
  if (cause instanceof ApiError) {
    if (cause.code === 'NETWORK') return '서버와 연결하지 못했어요. 인터넷 연결을 확인하고 잠시 후 다시 분석해주세요.'
    if (cause.status === 401 || cause.status === 403) return '로그인 상태를 확인한 뒤 다시 분석해주세요.'
    if (cause.status === 429) return '분석 요청이 많아요. 잠시 기다린 뒤 다시 분석해주세요.'
    if (cause.status === 504) return '분석 서버의 응답이 늦어지고 있어요. 잠시 후 다시 분석해주세요.'
    if (cause.status >= 500) return '분석 서비스에 일시적인 문제가 생겼어요. 잠시 후 다시 분석해주세요.'
    return cause.message
  }
  return cause instanceof Error && cause.message.includes('대기 시간이 초과')
    ? cause.message : '분석 결과를 받지 못했어요. 연결 상태를 확인하고 다시 분석해주세요.'
}

export default function AnalysisLoading({ imageUrl, run, onCancel, onComplete }: Props) {
  const [seconds, setSeconds] = useState(0)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const heading = useRef<HTMLHeadingElement>(null)
  const cancelAttempt = useRef<(() => void) | null>(null)
  const retryLocked = useRef(false)
  const latest = useRef({ run, onComplete })
  useEffect(() => { latest.current = { run, onComplete } })
  useEffect(() => { heading.current?.focus() }, [])
  useEffect(() => {
    cancelAttempt.current = startAnalysisAttempt({
      run: signal => latest.current.run(signal),
      onComplete: result => latest.current.onComplete(result),
      onError: cause => { retryLocked.current = false; setError(analysisError(cause)) },
      onTick: setSeconds,
    })
    return () => { cancelAttempt.current?.() }
  }, [attempt])

  function cancel() { cancelAttempt.current?.(); onCancel() }
  function retry() {
    if (!error || retryLocked.current) return
    retryLocked.current = true
    cancelAttempt.current?.()
    setError('')
    setSeconds(0)
    setAttempt(n => n + 1)
  }

  const delayed = seconds * 1000 >= ANALYSIS_DELAY_MS
  return (
    <section className={`analysis-loading${error ? ' analysis-has-error' : ''}`} aria-labelledby="analysis-heading">
      <p className="analysis-eyebrow">MOVAR · AI ANALYSIS</p>
      <h1 id="analysis-heading" ref={heading} tabIndex={-1}>{error ? '분석을 마치지 못했어요' : '두피 상태를 살펴보는 중'}</h1>
      <p className="analysis-intro">{error ? '잠시 후 다시 시도하거나 다른 사진으로 분석해주세요.' : '사진 분석과 상품 추천, 리포트를 준비하고 있어요.'}</p>
      <div className="analysis-lens">
        <div className="analysis-photo">
          <img src={imageUrl} alt="분석을 위해 촬영하거나 선택한 두피 사진" />
          {!error && <><div className="analysis-grid" aria-hidden="true" /><div className="analysis-laser" aria-hidden="true" /></>}
        </div>
      </div>
      {error ? <div className="capture-error" role="alert">{error}</div> : (
        <div className="analysis-progress">
          <div className="analysis-status"><strong role="status">{delayed ? '분석이 예상보다 오래 걸리고 있어요' : '분석 결과를 기다리고 있어요'}</strong><span aria-hidden="true">{Math.floor(seconds)}초</span></div>
          <div className="analysis-track" role="progressbar" aria-label="분석 응답 대기 중" aria-valuetext="진행 중">
            <div className="analysis-indeterminate" />
          </div>
          {delayed && <p className="analysis-delay">서버 상황에 따라 몇 분이 걸릴 수 있어요. 기다리거나 분석을 취소할 수 있어요.</p>}

        </div>
      )}
      <p className="analysis-disclaimer">AI 분석 결과는 참고용이며 의료진의 진단을 대체하지 않아요.</p>
      {error && <p className="analysis-retained">선택한 사진과 문진 답변은 그대로 유지돼요.</p>}
      <div className="analysis-actions">
        {error && <button className="button analysis-retry" onClick={retry}>다시 분석하기</button>}
        <button className="button capture-secondary analysis-cancel" onClick={cancel}>{error ? '사진·답변 확인하기' : '분석 취소'}</button>
      </div>
    </section>
  )
}
