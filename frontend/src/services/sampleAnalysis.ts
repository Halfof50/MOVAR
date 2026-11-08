import { sampleAnalysis } from '../data/sampleAnalysis'
import type { AnalysisResult } from './api'

// Explicit opt-in to the real pipeline when all AI services are ready.
export const isSampleAnalysis = import.meta.env.VITE_ANALYSIS_MODE !== 'live'

export function runSampleAnalysis(signal: AbortSignal): Promise<AnalysisResult> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(new DOMException('Cancelled', 'AbortError')); return }
    const abort = () => {
      clearTimeout(timer)
      signal.removeEventListener('abort', abort)
      reject(new DOMException('Cancelled', 'AbortError'))
    }
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', abort)
      resolve({ ...sampleAnalysis, report: { ...sampleAnalysis.report, analyzed_at: new Date().toISOString() } })
    }, 1500)
    signal.addEventListener('abort', abort, { once: true })
  })
}
