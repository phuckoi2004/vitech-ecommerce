import { useEffect } from 'react'
import CustomerLayout from '../layouts/CustomerLayout.jsx'

// Customer home page; its sections are added later.
export default function HomePage() {
  useEffect(() => {
    document.title = 'VieTech'
  }, [])

  return <CustomerLayout />
}
