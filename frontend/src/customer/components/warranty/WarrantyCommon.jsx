import { Link } from 'react-router-dom'
import { warrantyStage, warrantyStageLabel } from '../../../lib/warranty.js'
import { WARRANTY_HISTORY_PATH } from '../../routes/paths.js'

export function WarrantyStatus({ item }) {
  const stage = warrantyStage(item)
  return <span className="cw-status" data-stage={stage}>{warrantyStageLabel(stage)}</span>
}

export function WarrantyCard({ number, title, id, children }) {
  return <section className="cw-card" id={id} aria-labelledby={`${id}-title`}>
    <h2 id={`${id}-title`} className="cw-card-title">{number && <span>{number}</span>}{title}</h2>
    {children}
  </section>
}

export function WarrantyBreadcrumb({ current, backTo = WARRANTY_HISTORY_PATH }) {
  return <nav className="cw-breadcrumb" aria-label="Đường dẫn">
    <Link to="/tai-khoan">Tài khoản</Link><span aria-hidden="true">›</span>
    {current ? <><Link to={backTo}>Bảo hành và đổi trả</Link><span aria-hidden="true">›</span><span aria-current="page">{current}</span></>
      : <span aria-current="page">Bảo hành và đổi trả</span>}
  </nav>
}

export function WarrantyLoading({ label = 'Đang tải thông tin bảo hành…' }) {
  return <div className="cacc-loading is-compact" role="status"><span className="spinner" />{label}</div>
}

export function WarrantyError({ message, retry }) {
  return <div><p className="cacc-notice" role="alert">{message}</p>
    <button className="cacc-button is-outline cw-retry" type="button" onClick={retry}>Thử lại</button></div>
}
