import Button from '../../../components/shared/Button.jsx'
import Money from '../../../components/shared/Money.jsx'
import ConsultationButton from '../ConsultationButton.jsx'
import { productColorSwatch } from '../../../lib/product-colors.js'
import { canPurchase, colorLabel, variantPrice, versionLabel } from '../../../lib/product-detail.js'

// Display-only examples requested by the user; these never change a price, coupon or order.
const DEMO_OFFERS = [
  'Thu cũ lên đời: trợ giá đến 5 triệu đồng.',
  'Hỗ trợ trả góp 0% theo chương trình áp dụng.',
  'Ưu đãi thanh toán đến 2 triệu đồng tùy phương thức.',
  'Miễn phí giao hàng và hỗ trợ cài đặt cơ bản.',
]

export default function ProductPurchasePanel({ variants, variant, onSelect, busy, notice, ready, onCart, onBuy, onConsult }) {
  const versions = [...new Set(variants.map(versionLabel))]
  const colors = [...new Set(variants.filter((item) => item.Color?.trim()).map(colorLabel))]
  const selectedVersion = variant ? versionLabel(variant) : ''
  const selectedColor = variant ? colorLabel(variant) : ''
  const sameCombination = variants.filter((item) => versionLabel(item) === selectedVersion && colorLabel(item) === selectedColor)
  const purchasable = canPurchase(variant)
  const disabled = !!busy || !ready

  function selectVersion(version) {
    const candidates = variants.filter((item) => versionLabel(item) === version)
    onSelect(candidates.find((item) => colorLabel(item) === selectedColor)
      ?? candidates.find(canPurchase) ?? candidates[0])
  }

  return <section className="pd-card pd-purchase" aria-label="Thông tin mua hàng">
    <p className="pd-price">{variantPrice(variant) !== null ? <Money value={variant.Price} /> : <span className="pd-price-pending">Đang cập nhật giá</span>}</p>
    <div className="pd-option-group"><h2>Phiên bản</h2>
      {versions.length ? <div className="pd-options" role="group" aria-label="Chọn phiên bản">
        {versions.map((version) => <button type="button" key={version} className="pd-option" disabled={!!busy}
          aria-pressed={version === selectedVersion} onClick={() => selectVersion(version)}>{version}</button>)}
      </div> : <p className="pd-muted">Chưa có biến thể đang bán.</p>}
    </div>
    <div className="pd-option-group"><h2>Màu sắc</h2>
      {colors.length ? <div className="pd-options" role="group" aria-label="Chọn màu sắc">
        {colors.map((color) => {
          const candidate = variants.find((item) => versionLabel(item) === selectedVersion && colorLabel(item) === color)
          const swatch = productColorSwatch(color)
          return <button type="button" key={color} className="pd-option pd-color" aria-pressed={color === selectedColor}
            disabled={!!busy || !candidate} title={!candidate ? `Không có màu ${color} cho phiên bản ${selectedVersion}` : undefined}
            onClick={() => onSelect(candidate)}>
            {swatch && <span aria-hidden="true" className="pd-color-swatch" style={{ background: swatch }} />}{color}
          </button>
        })}
      </div> : <p className="pd-muted">Đang cập nhật màu sắc.</p>}
    </div>
    {sameCombination.length > 1 && <label className="pd-configuration">Cấu hình
      <select value={variant.ProductVariantId} disabled={!!busy}
        onChange={(event) => onSelect(variants.find((item) => item.ProductVariantId === event.target.value))}>
        {sameCombination.map((item) => <option key={item.ProductVariantId} value={item.ProductVariantId}>{item.VariantName}</option>)}
      </select>
    </label>}
    <p className={`pd-stock ${purchasable ? 'is-available' : ''}`} role="status">
      {!variant ? 'Chưa có phiên bản để đặt mua' : Number(variant.StockQuantity) <= 0 ? 'Hết hàng'
        : variantPrice(variant) === null ? 'Chưa có giá bán cho phiên bản này' : `Còn ${variant.StockQuantity} sản phẩm`}
    </p>
    <div className="pd-promotion"><div className="pd-promotion-heading"><h2>Ưu đãi khi mua hàng</h2><span className="pd-demo-badge">Nội dung demo</span></div>
      <ul>{DEMO_OFFERS.map((offer) => <li key={offer}>{offer}</li>)}</ul>
      <p className="pd-demo-note">Nội dung mẫu theo Figma; chưa áp dụng vào đơn hàng.</p>
    </div>
    <Button className="pd-buy" disabled={disabled || !purchasable} loading={busy === 'buy'} onClick={onBuy}>MUA NGAY</Button>
    <div className="pd-cta-row grid grid-cols-2 gap-2.5 max-[380px]:grid-cols-1">
      <Button variant="outline" className="pd-add" disabled={disabled || !purchasable} loading={busy === 'cart'} onClick={onCart}>Thêm vào giỏ hàng</Button>
      <ConsultationButton className="pd-consult" disabled={!ready} onStaff={onConsult} />
    </div>
    {notice && <p className={`pd-notice ${notice.ok ? 'is-success' : ''}`} role={notice.ok ? 'status' : 'alert'}>{notice.text}</p>}
  </section>
}
