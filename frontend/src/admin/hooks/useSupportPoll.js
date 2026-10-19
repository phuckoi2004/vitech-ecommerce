import { useCallback, useEffect, useState } from 'react'
import useInternalAuth from '../../hooks/useInternalAuth.js'

// Poll sequentially; retain the current conversation while refreshing, and never
// let a late response from a previous selection replace the newly selected one.
export default function useSupportPoll(load, reload = 0, enabled = true) {
  const { withAccessToken } = useInternalAuth()
  const [version, setVersion] = useState(0)
  const [state, setState] = useState({ load, reload, version, data: null, loading: true, error: '' })
  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()
    let timer, fetching = false
    async function poll() {
      if (fetching || document.hidden || controller.signal.aborted) return
      clearTimeout(timer)
      fetching = true
      try {
        const data = await withAccessToken((token) => load(token, controller.signal))
        if (!controller.signal.aborted) setState({ load, reload, version, data, loading: false, error: '' })
      } catch (failure) {
        if (!controller.signal.aborted) setState((previous) => ({ load, reload, version, data: previous.load === load ? previous.data : null, loading: false, error: failure.message || 'Không tải được cuộc trò chuyện.' }))
      } finally {
        fetching = false
        if (!controller.signal.aborted) timer = setTimeout(poll, 5000)
      }
    }
    void poll()
    document.addEventListener('visibilitychange', poll)
    return () => { controller.abort(); clearTimeout(timer); document.removeEventListener('visibilitychange', poll) }
  }, [load, withAccessToken, version, reload, enabled])
  const refresh = useCallback(() => {
    setState((previous) => ({ ...previous, loading: true }))
    setVersion((previous) => previous + 1)
  }, [])
  const current = state.load === load && state.reload === reload && state.version === version
  return { ...(current ? state : { data: state.load === load ? state.data : null, loading: true, error: '' }), refresh }
}
