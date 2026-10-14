import { useCallback } from 'react'
import { request } from '../services/api/client.js'
import useCustomerSession from './useCustomerSession.js'

// The auth provider rotates expired access tokens and the server checks ownership.
export default function useCustomerRequest() {
  const { withAccessToken } = useCustomerSession()
  return useCallback((path, options = {}) => withAccessToken((accessToken) =>
    request(path, { ...options, accessToken })), [withAccessToken])
}
