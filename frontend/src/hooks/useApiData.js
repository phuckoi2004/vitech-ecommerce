import { useCallback, useEffect, useEffectEvent, useState } from 'react'

// Loads data for `key` and reloads when the key changes. `load(signal)` returns a promise; `key` must name
// everything the request depends on, because a new `load` alone does not start a request. A null key loads
// nothing yet. Results of an older key or an aborted request are ignored.
export default function useApiData(key, load) {
  const [result, setResult] = useState(null)
  const [attempt, setAttempt] = useState(0)
  const start = useEffectEvent((signal) => load(signal))

  useEffect(() => {
    if (key === null) return undefined
    const controller = new AbortController()
    start(controller.signal)
      .then((data) => setResult({ key, attempt, data, error: '' }))
      .catch((failure) => {
        if (!controller.signal.aborted) setResult({ key, attempt, data: null, error: failure?.message || 'Không thể tải dữ liệu.' })
      })
    return () => controller.abort()
  }, [key, attempt])

  const reload = useCallback(() => setAttempt((count) => count + 1), [])
  const current = result && result.key === key && result.attempt === attempt ? result : null
  return { loading: key !== null && !current, data: current?.data, error: current?.error ?? '', reload }
}
