import { Link, useSearchParams } from 'react-router-dom'
import { RETURN_HISTORY_PATH, WARRANTY_HISTORY_PATH } from '../../routes/paths.js'
import WarrantyHistory from '../warranty/WarrantyHistory.jsx'
import ReturnHistory from './ReturnHistory.jsx'

export default function ServiceHistory() {
  const [params] = useSearchParams()
  const isReturn = params.get('type') === 'return'
  return <>
    <nav className="cw-service-tabs" aria-label="Loại yêu cầu">
      <Link to={WARRANTY_HISTORY_PATH} aria-current={!isReturn ? 'page' : undefined}>Bảo hành</Link>
      <Link to={RETURN_HISTORY_PATH} aria-current={isReturn ? 'page' : undefined}>Đổi/trả</Link>
    </nav>
    {isReturn ? <ReturnHistory /> : <WarrantyHistory />}
  </>
}
