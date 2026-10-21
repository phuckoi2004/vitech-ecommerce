import Button from '../../../components/shared/Button.jsx'
import Money from '../../../components/shared/Money.jsx'
import { formatDiscountPercent } from '../../../lib/format.js'
import ConsultationButton from '../ConsultationButton.jsx'
import { productColorSwatch } from '../../../lib/product-colors.js'
import { canPurchase, colorLabel, variantPrice, versionLabel } from '../../../lib/product-detail.js'

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
    <div className="pd-price-block">
      <p className="pd-price">{variantPrice(variant) !== null ? <Money value={variantPrice(variant)} /> : <span className="pd-price-pending">Đang cập nhật giá</span>}</p>
      {Number(variant?.OriginalPrice) > variantPrice(variant) && <div className="pd-price-details">
        <p className="pd-original-row"><span className="sr-only">Giá niêm yết </span><del><Money value={variant.OriginalPrice} /></del><strong><span className="sr-only">Giảm </span>-{formatDiscountPercent(variant.DiscountPercent)}</strong></p>
        <p className="pd-price-saving">Tiết kiệm <Money value={variant.DiscountAmount} /></p>
      </div>}
    </div>
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
    <Button className="pd-buy" disabled={disabled || !purchasable} loading={busy === 'buy'} onClick={onBuy}>MUA NGAY</Button>
    <div className="pd-cta-row grid grid-cols-2 gap-2.5 max-[380px]:grid-cols-1">
      <Button variant="outline" className="pd-add" disabled={disabled || !purchasable} loading={busy === 'cart'} onClick={onCart}>Thêm vào giỏ hàng</Button>
      <ConsultationButton className="pd-consult" disabled={!ready} onStaff={onConsult} />
    </div>
    {notice && <p className={`pd-notice ${notice.ok ? 'is-success' : ''}`} role={notice.ok ? 'status' : 'alert'}>{notice.text}</p>}
  </section>
}
