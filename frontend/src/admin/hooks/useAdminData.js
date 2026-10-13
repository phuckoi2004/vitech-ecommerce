import { useEffect, useState } from 'react'
import { getAdminData } from '../../lib/admin-dashboard-api.js'

// Abort obsolete reads on navigation/filter changes, and keep network errors distinct from an empty result.
export default function useAdminData(withAccessToken, path, params = {}, version = 0) {
  const query = JSON.stringify(params)
  const [state, setState] = useState({ data: null, loading: true, error: '' })
  useEffect(() => {
    const controller = new AbortController()
    setState({ data: null, loading: true, error: '' })
    if (!path) {
      setState({ data: null, loading: false, error: '' })
      return () => controller.abort()
    }
    withAccessToken((token) => getAdminData(token, path, JSON.parse(query), controller.signal))
      .then((data) => { if (!controller.signal.aborted) setState({ data, loading: false, error: '' }) })
      .catch((failure) => { if (!controller.signal.aborted) setState({ data: null, loading: false, error: failure.message }) })
    return () => controller.abort()
  }, [withAccessToken, path, query, version])
  return state
}
