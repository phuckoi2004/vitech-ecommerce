import { BadgeIcon, ReturnIcon, ShieldIcon, TruckIcon } from '../icons.jsx'

// Figma "Trust Benefits". "Trả góp 0%" is replaced: the project has no installment payment (COD and QR only).
const BENEFITS = [
  ['Giao hàng nhanh', 'Toàn quốc'],
  ['Sản phẩm chính hãng', '100% chính hãng'],
  ['Giá tốt mỗi ngày', 'Nhiều ưu đãi'],
  ['Thanh toán linh hoạt', 'COD hoặc chuyển khoản QR'],
  ['Tư vấn mua hàng', 'Chat với nhân viên'],
]

export function TrustBar() {
  return <section className="home-trust home-card is-raised" aria-label="Cam kết của VieTech">
    <ul>
      {BENEFITS.map(([title, detail]) => <li key={title}><strong>{title}</strong><span>{detail}</span></li>)}
    </ul>
  </section>
}

// Shopping policies. The 7-day return window is the backend default (RETURN_WINDOW_DAYS).
const POLICIES = [
  { title: 'Giao hàng nhanh', detail: 'Toàn quốc • 1–3 ngày', Icon: TruckIcon },
  { title: 'Đổi trả dễ dàng', detail: 'Trong 7 ngày', Icon: ReturnIcon },
  { title: 'Thanh toán an toàn', detail: 'Nhiều hình thức', Icon: ShieldIcon },
  { title: 'Bảo hành chính hãng', detail: 'Hỗ trợ toàn quốc', Icon: BadgeIcon },
]

export function PolicySection() {
  return <section className="home-policies" aria-labelledby="home-policies-title">
    <div className="home-policy-block home-card">
      <h2 id="home-policies-title" className="home-title is-small">Chính sách mua hàng tại VieTech</h2>
      <ul className="home-policy-list">
        {POLICIES.map(({ title, detail, Icon }) => <li key={title} className="home-policy">
          <span className="home-policy-icon"><Icon /></span>
          <strong>{title}</strong>
          <span>{detail}</span>
        </li>)}
      </ul>
    </div>
  </section>
}
