import { useEffect } from 'react'

// Customer home page, rendered inside CustomerLayout; its sections are added later.
export default function HomePage() {
  useEffect(() => {
    document.title = 'VieTech'
  }, [])

  return null
}
