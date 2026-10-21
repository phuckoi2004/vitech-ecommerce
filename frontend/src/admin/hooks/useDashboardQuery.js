import { useCallback, useEffect, useState } from 'react'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { getAdminData } from '../../services/api/admin.js'

// Refresh sequentially while visible. Retain the last successful data during a
// background refresh, cancel on navigation, and never accept an older query's result.
export function useDashboardLoad(load, enabled = true, intervalMs = 60000) {
  const { withAccessToken } = useInternalAuth()
  const [version, setVersion] = useState(0)
  const [state, setState] = useState({ load, enabled, data: null, loading: enabled, refreshing: false, error: '' })
  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()
    let timer, fetching = false, lastStarted = -Infinity
    async function refresh(force = false) {
      if (fetching || document.hidden || controller.signal.aborted || (!force && Date.now() - lastStarted < 1000)) return
      clearTimeout(timer)
      fetching = true
      lastStarted = Date.now()
      setState((previous) => ({ load, enabled, data: previous.load === load ? previous.data : null,
        updatedAt: previous.load === load ? previous.updatedAt : null,
        loading: previous.load !== load || !previous.data, refreshing: true, error: '' }))
      try {
        const data = await withAccessToken((token) => load(token, controller.signal))
        if (!controller.signal.aborted) setState({ load, enabled, data, loading: false, refreshing: false, error: '', updatedAt: new Date() })
      } catch (failure) {
        if (!controller.signal.aborted) setState((previous) => ({ ...previous, loading: false, refreshing: false, error: failure.message || 'Không tải được dữ liệu.' }))
      } finally {
        fetching = false
        if (!controller.signal.aborted && intervalMs > 0) timer = window.setTimeout(() => refresh(true), intervalMs)
      }
    }
    const onReturn = () => { void refresh() }
    void refresh(true)
    window.addEventListener('focus', onReturn)
    document.addEventListener('visibilitychange', onReturn)
    return () => {
      controller.abort()
      clearTimeout(timer)
      window.removeEventListener('focus', onReturn)
      document.removeEventListener('visibilitychange', onReturn)
    }
  }, [load, enabled, intervalMs, version, withAccessToken])
  const refresh = useCallback(() => setVersion((value) => value + 1), [])
  const current = state.load === load && state.enabled === enabled
  return { ...(current ? state : { data: null, loading: enabled, refreshing: false, error: '' }), refresh }
}

export default function useDashboardQuery(path, query = {}, enabled = true, intervalMs = 60000) {
  const serialized = JSON.stringify(query)
  const load = useCallback((token, signal) => getAdminData(token, path, JSON.parse(serialized), signal), [path, serialized])
  return useDashboardLoad(load, enabled, intervalMs)
}
