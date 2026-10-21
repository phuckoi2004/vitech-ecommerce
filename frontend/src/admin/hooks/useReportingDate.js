import { useEffect, useState } from 'react'
import { vietnamToday } from '../../lib/dashboard-periods.js'

export default function useReportingDate() {
  const [today, setToday] = useState(vietnamToday)
  useEffect(() => {
    const update = () => setToday(vietnamToday())
    const interval = window.setInterval(update, 30000)
    window.addEventListener('focus', update)
    document.addEventListener('visibilitychange', update)
    return () => {
      window.clearInterval(interval)
      window.removeEventListener('focus', update)
      document.removeEventListener('visibilitychange', update)
    }
  }, [])
  return today
}
