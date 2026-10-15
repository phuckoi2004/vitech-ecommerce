import { Navigate, useSearchParams } from 'react-router-dom'

export default function LegacyContentRedirect() {
  const [params] = useSearchParams()
  const target = params.get('tab') === '1' ? '/admin/banners' : '/admin/news'
  const next = new URLSearchParams(params)
  next.delete('tab')
  return <Navigate replace to={target + (next.size ? '?' + next.toString() : '')} />
}
