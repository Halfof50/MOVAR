import assert from 'node:assert/strict'
import { createServer } from 'vite'
const server = await createServer({ server: { middlewareMode: true } })
const flush = () => new Promise(resolve => setImmediate(resolve))
try {
  const { startAnalysisAttempt } = await server.ssrLoadModule('/src/services/analysisAttempt.ts')
  let requests = 0, completed = 0, errors = 0, signal, resolveRequest
  const options = {
    run: s => { requests++; signal = s; return new Promise(resolve => { resolveRequest = resolve }) },
    onComplete: () => completed++, onError: () => errors++, onTick: () => {},
  }
  startAnalysisAttempt(options)()
  const stop = startAnalysisAttempt(options)
  await flush()
  assert.equal(requests, 1)
  stop()
  assert.equal(signal.aborted, true)
  resolveRequest({})
  await flush()
  assert.equal(completed, 0)
  assert.equal(errors, 0)
  let timeoutMessage
  await new Promise(resolve => {
    startAnalysisAttempt({ ...options, timeoutMs: 10,
      onError: cause => { timeoutMessage = cause.message; resolve() },
    })
  })
  assert.match(timeoutMessage, /대기 시간이 초과/)
  assert.equal(signal.aborted, true)
  resolveRequest({})
  await flush()
  assert.equal(completed, 0)
  startAnalysisAttempt({ ...options, run: async s => { assert.equal(s.aborted, false); return 'ok' },
    onComplete: value => { assert.equal(value, 'ok'); completed++ },
  })
  await flush()
  assert.equal(completed, 1)
  startAnalysisAttempt({ ...options, run: () => { throw new Error('offline') } })
  await flush()
  assert.equal(errors, 1)
  console.log('PASS: StrictMode single request, unmount cancellation, stale result suppression, deadline, retry success, synchronous failure')
} finally { await server.close() }
