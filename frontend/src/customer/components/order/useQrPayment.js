import { useEffect, useEffectEvent, useRef, useState } from 'react'
import useCustomerSession from '../../../hooks/useCustomerSession.js'
import { createQrPayment } from '../../../lib/order-api.js'

// The pending QR payment of an order (POST /orders/{id}/payments/qr): asked while `needed`, once per order and
// attempt. Asking again (retry(), or the page opened again) returns the same pending QR, never a new order. Asked only
// once even when StrictMode runs effects twice: two requests at the same time would make the second one fail with
// qr_payment_in_progress. Returns {qr, failure, loading, retry}.
export default function useQrPayment(orderId, needed) {
  const { withAccessToken } = useCustomerSession()
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState(null)
  const asked = useRef(null)
  const key = `${orderId}:${attempt}`

  const ask = useEffectEvent((askedKey) => {
    withAccessToken((token) => createQrPayment(token, orderId))
      .then((qr) => setResult({ key: askedKey, qr }))
      .catch((failure) => setResult({ key: askedKey, failure }))
  })

  useEffect(() => {
    if (!needed || asked.current === key) return
    asked.current = key
    ask(key)
  }, [needed, key])

  const current = result?.key === key ? result : null
  return { qr: current?.qr ?? null, failure: current?.failure ?? null, loading: needed && !current,
    retry: () => setAttempt((value) => value + 1) }
}
