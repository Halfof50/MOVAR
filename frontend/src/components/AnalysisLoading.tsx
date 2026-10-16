import { useEffect, useRef, useState } from 'react'
import './AnalysisLoading.css'

type Props = { imageUrl: string; onCancel: () => void; onComplete: () => void }

/** UI demo only. Replace the timer with the analysis API lifecycle when available. */
export default function AnalysisLoading({ imageUrl, onCancel, onComplete }: Props) {
  const [progress, setProgress] = useState(0)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    heading.current?.focus()
    const start = performance.now()
    const timer = window.setInterval(() => {
      setProgress(Math.min(100, Math.floor((performance.now() - start) / 60)))
    }, 60)
    const completion = window.setTimeout(onComplete, 6400)
    return () => { window.clearInterval(timer); window.clearTimeout(completion) }
  }, [onComplete])

  const status = progress < 25 ? '사진 준비 중' : progress < 70 ? '두피를 살펴보는 중' : progress < 100 ? '결과 화면 준비 중' : '화면으로 이동 중'
  return (
    <section className="analysis-loading" aria-labelledby="analysis-heading">
      <p className="analysis-eyebrow">MOVAR · DEMO ANALYSIS</p>
      <h1 id="analysis-heading" ref={heading} tabIndex={-1}>두피 상태를 살펴보는 중</h1>
      <p className="analysis-intro">잠시만 기다려주세요</p>
      <div className="analysis-lens">
        <div className="analysis-photo">
          <img src={imageUrl} alt="분석을 위해 촬영하거나 선택한 두피 사진" />
          <div className="analysis-grid" aria-hidden="true" />
          <div className="analysis-laser" aria-hidden="true" />
        </div>
      </div>
      <div className="analysis-progress">
        <div className="analysis-status"><strong role="status">{status}</strong><span aria-hidden="true">{progress}%</span></div>
        <div className="analysis-track" role="progressbar" aria-label="데모 화면 진행률" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
          <div style={{ width: `${progress}%` }} />
        </div>
      </div>
      <p className="analysis-disclaimer">실제 AI 분석이 아닌 화면 체험용 데모입니다.</p>
      <button className="button capture-secondary analysis-cancel" onClick={onCancel}>× &nbsp; 분석 취소</button>
    </section>
  )
}
