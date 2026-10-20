import { useState } from 'react'
import { Link } from 'react-router-dom'
import Money from '../../../components/shared/Money.jsx'
import { formatDateTime } from '../../../lib/format.js'
import { INFO_PATHS } from '../../routes/paths.js'
import { timeLeft } from './orderPayment.js'

const COPIED = {
  account: 'Đã sao chép số tài khoản.',
  amount: 'Đã sao chép số tiền.',
  content: 'Đã sao chép nội dung chuyển khoản.',
}

// The transfer details of a pending QR payment (QrPaymentResponse), shown as the server sent them: nothing is read
// out of the QR image URL. Bank, AccountNumber, AccountName and ExpiresAt may be null. `now` (ms) drives the countdown;
// `onCheck()` reads the order again at once (the page also reads it every few seconds).
export default function QrPayment({ qr, now, onCheck }) {
  const [copied, setCopied] = useState(null)
  const deadline = qr.ExpiresAt ? Date.parse(qr.ExpiresAt) : null

  async function copy(what, text) {
    try {
      await navigator.clipboard.writeText(text)
      setCopied({ what, ok: true })
    } catch {
      setCopied({ what, ok: false })
    }
  }

  return <section className="order-qr" aria-labelledby="order-qr-title">
    <div className="order-qr-head">
      <h2 id="order-qr-title" className="order-section-title">Quét mã QR để thanh toán</h2>
      <span className="order-pill is-waiting">Chờ thanh toán</span>
    </div>
    <div className="order-qr-body">
      <div className="order-qr-code">
        {qr.QrData ? <img className="order-qr-image" src={qr.QrData} alt="Mã QR chuyển khoản cho đơn hàng" width="240" height="240" />
          : <p className="order-qr-noimage">Không hiển thị được mã QR. Hãy chuyển khoản theo thông tin bên cạnh.</p>}
        {deadline !== null && <p className="order-qr-timer">Còn <span className="order-qr-countdown">{timeLeft(deadline, now)}</span></p>}
      </div>
      <div className="order-qr-info">
        <dl className="order-qr-details">
          <div><dt>Ngân hàng</dt><dd>{qr.Bank || 'Xem trong mã QR'}</dd></div>
          <div>
            <dt>Số tài khoản</dt>
            <dd className="order-qr-copyable">
              {qr.AccountNumber ? <>
                <span>{qr.AccountNumber}</span>
                <button type="button" className="order-copy" onClick={() => copy('account', qr.AccountNumber)}
                  aria-label={`Sao chép số tài khoản ${qr.AccountNumber}`}>Sao chép</button>
              </> : 'Xem trong mã QR'}
            </dd>
          </div>
          {qr.AccountName && <div><dt>Chủ tài khoản</dt><dd>{qr.AccountName}</dd></div>}
          <div>
            <dt>Số tiền</dt>
            <dd className="order-qr-copyable">
              <Money className="order-qr-amount" value={qr.TransferAmount} />
              <button type="button" className="order-copy" onClick={() => copy('amount', String(qr.TransferAmount))}
                aria-label="Sao chép số tiền cần chuyển">Sao chép</button>
            </dd>
          </div>
          <div>
            <dt>Nội dung chuyển khoản</dt>
            <dd className="order-qr-copyable order-qr-content">
              <strong>{qr.TransferContent}</strong>
              <button type="button" className="order-copy" onClick={() => copy('content', qr.TransferContent)}
                aria-label={`Sao chép nội dung chuyển khoản ${qr.TransferContent}`}>Sao chép</button>
            </dd>
          </div>
          {deadline !== null && <div><dt>Hạn thanh toán</dt><dd>{formatDateTime(qr.ExpiresAt)}</dd></div>}
        </dl>
        <p className="order-qr-copied" role="status">
          {!copied ? '' : copied.ok ? COPIED[copied.what]
            : 'Không sao chép được. Hãy chọn và sao chép thủ công.'}
        </p>
      </div>
    </div>
    <ol className="order-qr-steps">
      <li>Mở ứng dụng ngân hàng và quét mã QR, hoặc nhập thông tin chuyển khoản ở trên.</li>
      <li>Giữ nguyên số tiền và nội dung chuyển khoản: VieTech dùng nội dung này để nhận ra đơn hàng của bạn.</li>
      <li>Xác nhận chuyển khoản. Trang này tự cập nhật khi VieTech nhận được thanh toán.</li>
    </ol>
    <div className="order-qr-waiting">
      <p><span className="order-qr-pulse" aria-hidden="true" />Đang chờ VieTech nhận thanh toán…</p>
      <button type="button" className="order-link-button" onClick={onCheck}>Kiểm tra thanh toán</button>
    </div>
    <p className="order-note">
      Đã chuyển khoản nhưng sau vài phút trang vẫn chưa cập nhật? <Link to={INFO_PATHS.contact}>Liên hệ VieTech</Link> kèm
      mã đơn hàng để được hỗ trợ.
    </p>
  </section>
}
