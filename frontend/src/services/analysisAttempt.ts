// Backend stages can take 60s (vision) + 300s (recommendation) + 60s (report).
export const ANALYSIS_DELAY_MS = 30_000
export const ANALYSIS_TIMEOUT_MS = 480_000

export function startAnalysisAttempt<T>(options: {
  run: (signal: AbortSignal) => Promise<T>
  onComplete: (result: T) => void
  onError: (cause: unknown) => void
  onTick: (seconds: number) => void
  timeoutMs?: number
}) {
  const controller = new AbortController()
  let active = true
  let tick: ReturnType<typeof setInterval> | undefined
  let deadline: ReturnType<typeof setTimeout> | undefined
  function stop() {
    active = false
    clearInterval(tick)
    clearTimeout(deadline)
    controller.abort()
  }
  // Defer until after StrictMode's setup/cleanup replay, preventing a duplicate POST.
  queueMicrotask(() => {
    if (!active) return
    const start = Date.now()
    tick = setInterval(() => { if (active) options.onTick((Date.now() - start) / 1000) }, 250)
    deadline = setTimeout(() => {
      if (!active) return
      stop()
      options.onError(new Error('분석 응답 대기 시간이 초과됐어요. 잠시 후 다시 분석해주세요.'))
    }, options.timeoutMs ?? ANALYSIS_TIMEOUT_MS)
    Promise.resolve().then(() => {
      if (!active) return
      return options.run(controller.signal)
    }).then(result => {
      if (!active) return
      stop()
      options.onComplete(result as T)
    }, cause => {
      if (!active) return
      stop()
      options.onError(cause)
    })
  })
  return stop
}
