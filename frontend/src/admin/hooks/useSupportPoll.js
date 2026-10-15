import { useCallback, useEffect, useState } from 'react'
import useInternalAuth from '../../hooks/useInternalAuth.js'

// Poll sequentially; retain the current conversation while refreshing, and never
// let a late response from a previous selection replace the newly selected one.
export default function useSupportPoll(load, reload = 0) {
  const { withAccessToken } = useInternalAuth()
  const [version, setVersion] = useState(0)
  const [state, setState] = useState({ load, data: null, loading: true, error: '' })
  useEffect(() => {
    const controller = new AbortController()
    let timer
    async function poll() {
      try {
        const data = await withAccessToken((token) => load(token, controller.signal))
        if (!controller.signal.aborted) setState({ load, data, loading: false, error: '' })
      } catch (failure) {
        if (!controller.signal.aborted) setState((previous) => ({ load, data: previous.load === load ? previous.data : null, loading: false, error: failure.message || 'Không tải được cuộc trò chuyện.' }))
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(poll, 5000)
      }
    }
    void poll()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [load, withAccessToken, version, reload])
  const refresh = useCallback(() => {
    setState((previous) => ({ ...previous, loading: true }))
    setVersion((previous) => previous + 1)
  }, [])
  return { ...(state.load === load ? state : { data: null, loading: true, error: '' }), refresh }
}
