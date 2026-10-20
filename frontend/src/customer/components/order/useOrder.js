import { useCallback, useEffect, useState } from 'react'
import useCustomerSession from '../../../hooks/useCustomerSession.js'
import { getOrder } from '../../../lib/order-api.js'

const readsOf = (state, orderId) => (state?.orderId === orderId ? state.reads : 0)

// The customer's order as the server has it (GET /orders/{id}), read when the page opens and on refresh().
// `read(signal)` reads it again for a poller: the last order read stays shown meanwhile, a failed read keeps it and
// sets `error`, and an aborted read changes nothing. `reads` counts finished reads, so a poller can schedule the next
// read after each answer (one request at a time). `replace(order)` takes an order another call returned (cancel).
export default function useOrder(orderId) {
  const { withAccessToken } = useCustomerSession()
  const [state, setState] = useState(null)
  const [version, setVersion] = useState(0)

  // {data} or {failure}; the state changes only in `apply`, after the answer.
  const load = useCallback(async (signal) => {
    try {
      return { data: await withAccessToken((token) => getOrder(token, orderId, { signal })) }
    } catch (failure) {
      return { failure }
    }
  }, [orderId, withAccessToken])
  const apply = useCallback(({ data, failure }) => {
    setState((previous) => ({ orderId, data: data ?? (previous?.orderId === orderId ? previous.data : null),
      error: failure ? failure.message || 'Không thể tải đơn hàng.' : '', reads: readsOf(previous, orderId) + 1 }))
  }, [orderId])
  const read = useCallback((signal) => load(signal).then((result) => {
    if (!signal.aborted) apply(result)
  }), [load, apply])

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal).then((result) => {
      if (!controller.signal.aborted) apply(result)
    })
    return () => controller.abort()
  }, [load, apply, version])

  const refresh = useCallback(() => setVersion((value) => value + 1), [])
  const replace = useCallback((data) => {
    setState((previous) => ({ orderId, data, error: '', reads: readsOf(previous, orderId) + 1 }))
  }, [orderId])

  const current = state?.orderId === orderId ? state : null
  return { order: current?.data ?? null, error: current?.error ?? '', loading: !current, reads: current?.reads ?? 0, read,
    refresh, replace }
}
