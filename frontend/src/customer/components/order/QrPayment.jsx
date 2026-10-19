import { useState } from 'react'
import Money from '../../../components/shared/Money.jsx'
import { formatDateTime } from '../../../lib/format.js'
import { timeLeft } from './orderPayment.js'

// The transfer details of a pending QR payment (QrPaymentResponse), shown as the server sent them: nothing is read
// out of the QR image URL. Bank, AccountNumber and ExpiresAt may be null. `now` (ms) drives the countdown.
export default function QrPayment({ qr, now }) {
  const [copied, setCopied] = useState(null)
  const deadline = qr.ExpiresAt ? Date.parse(qr.ExpiresAt) : null

  async function copyContent() {
    try {
      await navigator.clipboard.writeText(qr.TransferContent)
      setCopied('done')
    } catch {
      setCopied('failed')
    }
  }

  return <section className="order-qr" aria-labelledby="order-qr-title">
    <h2 id="order-qr-title" className="order-section-title">Quét mã QR để thanh toán</h2>
    <div className="order-qr-body">
      {qr.QrData ? <img className="order-qr-image" src={qr.QrData} alt="Mã QR chuyển khoản cho đơn hàng" width="240" height="240" />
        : <p className="order-qr-noimage">Không hiển thị được mã QR. Hãy chuyển khoản theo thông tin bên cạnh.</p>}
      <dl className="order-qr-details">
        <div><dt>Ngân hàng</dt><dd>{qr.Bank || 'Xem trong mã QR'}</dd></div>
        <div><dt>Số tài khoản</dt><dd>{qr.AccountNumber || 'Xem trong mã QR'}</dd></div>
        <div><dt>Số tiền</dt><dd className="order-qr-amount"><Money value={qr.TransferAmount} /></dd></div>
        <div>
          <dt>Nội dung chuyển khoản</dt>
          <dd className="order-qr-content">
            <strong>{qr.TransferContent}</strong>
            <button type="button" onClick={copyContent} aria-label={`Sao chép nội dung chuyển khoản ${qr.TransferContent}`}>Sao chép</button>
          </dd>
        </div>
        {deadline !== null && <div>
          <dt>Hạn thanh toán</dt>
          <dd>{formatDateTime(qr.ExpiresAt)} · còn <span className="order-qr-countdown">{timeLeft(deadline, now)}</span></dd>
        </div>}
      </dl>
    </div>
    <p className="order-qr-copied" role="status">
      {copied === 'done' ? 'Đã sao chép nội dung chuyển khoản.'
        : copied === 'failed' ? 'Không sao chép được. Hãy chọn và sao chép nội dung chuyển khoản thủ công.' : ''}
    </p>
    <p className="order-note">
      Chuyển đúng số tiền và nội dung chuyển khoản. Trang này tự cập nhật khi VieTech nhận được thanh toán.
    </p>
  </section>
}
