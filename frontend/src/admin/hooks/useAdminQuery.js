import { useCallback, useEffect, useState } from 'react'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { getAdminData } from '../../services/api/admin.js'

export function useAdminLoad(load, enabled = true) {
  const { withAccessToken } = useInternalAuth()
  const [version, setVersion] = useState(0)
  const [state, setState] = useState({ load, enabled, data: null, loading: enabled, error: '' })
  useEffect(() => {
    const controller = new AbortController()
    setState({ load, enabled, data: null, loading: enabled, error: '' })
    if (enabled) {
      withAccessToken((token) => load(token, controller.signal))
        .then((data) => { if (!controller.signal.aborted) setState({ load, enabled, data, loading: false, error: '', updatedAt: new Date() }) })
        .catch((failure) => { if (!controller.signal.aborted) setState({ load, enabled, data: null, loading: false, error: failure.message }) })
    }
    return () => controller.abort()
  }, [withAccessToken, load, enabled, version])
  const refresh = useCallback(() => setVersion((value) => value + 1), [])
  // Never expose a previous query's rows/count during the render before its effect resets state.
  return { ...(state.load === load && state.enabled === enabled ? state : { data: null, loading: enabled, error: '' }), refresh }
}

export default function useAdminQuery(path, query = {}, enabled = true) {
  const serialized = JSON.stringify(query)
  const load = useCallback((token, signal) => getAdminData(token, path, JSON.parse(serialized), signal), [path, serialized])
  return useAdminLoad(load, enabled)
}
