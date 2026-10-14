import { useEffect, useState } from 'react'
import { browserMonth } from '../../lib/dashboard-periods.js'

export default function useBrowserMonth() {
  const [month, setMonth] = useState(browserMonth)
  useEffect(() => {
    const update = () => setMonth(browserMonth())
    const interval = window.setInterval(update, 30000)
    window.addEventListener('focus', update)
    document.addEventListener('visibilitychange', update)
    return () => {
      window.clearInterval(interval)
      window.removeEventListener('focus', update)
      document.removeEventListener('visibilitychange', update)
    }
  }, [])
  return month
}
