import { useSearchParams } from 'react-router-dom'
import useApiData from '../../hooks/useApiData.js'
import useCustomerSession from '../../hooks/useCustomerSession.js'
import { getExchange } from '../../lib/return-api.js'

export const exchangePath = (path, id, extra = {}) => `${path}?${new URLSearchParams({ exchange: id, ...extra })}`

// URL-scoped: leaving these links (e.g. using the logo) restores ordinary shopping without touching the cart.
export default function useExchange() {
  const [params] = useSearchParams()
  const id = params.get('exchange') || ''
  const { user, withAccessToken } = useCustomerSession()
  const state = useApiData(id ? `exchange:${user?.UserId}:${id}` : null,
    (signal) => withAccessToken((token) => getExchange(token, id, { signal })))
  return { ...state, id, active: !!id }
}
