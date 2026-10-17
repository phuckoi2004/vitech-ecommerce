import { useEffect, useState } from 'react'

// Keep date-derived labels current while the admin page remains open.
export function useCouponClock(clock = Date.now) {
  const [now, setNow] = useState(clock)
  useEffect(() => {
    const timer = window.setInterval(() => setNow(clock()), 1000)
    return () => window.clearInterval(timer)
  }, [clock])
  return now
}

// Poll only read-only views; a refresh must never remount an in-progress editor.
export default function useCouponRefresh(refresh, enabled) {
  useEffect(() => {
    if (!enabled) return
    const update = () => { if (document.visibilityState !== 'hidden') refresh() }
    const timer = window.setInterval(update, 30000)
    window.addEventListener('focus', update)
    return () => { window.clearInterval(timer); window.removeEventListener('focus', update) }
  }, [enabled, refresh])
}
