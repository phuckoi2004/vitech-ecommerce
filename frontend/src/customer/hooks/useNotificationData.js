import { useCallback, useEffect, useEffectEvent, useState } from 'react'

// Refresh in the background without blanking existing data or overlapping requests.
export default function useNotificationData(key, load) {
  const [state, setState] = useState(null)
  const [attempt, setAttempt] = useState(0)
  const start = useEffectEvent((signal) => load(signal))
  useEffect(() => {
    if (key === null) return undefined
    const controller = new AbortController()
    let timer, fetching = false, queued = false
    async function refresh() {
      if (document.hidden || controller.signal.aborted) return
      if (fetching) { queued = true; return }
      clearTimeout(timer)
      fetching = true
      setState(previous => ({ key, data: previous?.key === key ? previous.data : null, error: previous?.key === key ? previous.error : '', refreshing: true }))
      try {
        const data = await start(controller.signal)
        if (!controller.signal.aborted) setState({ key, data, error: '', refreshing: false })
      } catch (failure) {
        if (!controller.signal.aborted) setState(previous => ({ key, data: previous?.key === key ? previous.data : null, error: failure.message || 'Không tải được thông báo.', refreshing: false }))
      } finally {
        fetching = false
        if (!controller.signal.aborted) {
          if (queued) { queued = false; void refresh() }
          else timer = setTimeout(refresh, 30000)
        }
      }
    }
    void refresh()
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    window.addEventListener('vietech-notifications-changed', refresh)
    return () => {
      controller.abort(); clearTimeout(timer)
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', refresh)
      window.removeEventListener('vietech-notifications-changed', refresh)
    }
  }, [key, attempt])
  const reload = useCallback(() => setAttempt(value => value + 1), [])
  const current = state?.key === key ? state : null
  return { data: current?.data, error: current?.error ?? '', loading: key !== null && !current?.data && !current?.error, refreshing: current?.refreshing ?? false, reload }
}
