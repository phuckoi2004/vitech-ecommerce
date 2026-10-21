import { Link } from 'react-router-dom'
import Money from '../../../components/shared/Money.jsx'
import { productPath } from '../../routes/paths.js'
import StoreImage from '../StoreImage.jsx'
import { LOW_STOCK, lineDisplay, lineStatus } from './cartLines.js'
import QuantityStepper from './QuantityStepper.jsx'

const STOCK_TEXT = { soldOut: 'Hết hàng', stopped: 'Ngừng kinh doanh', overStock: 'Vượt tồn kho' }

// Figma "Cart Item": checkbox, image, name, variant, price, actions and the quantity column, with a notice under it
// when the line is at its stock limit or cannot be bought. `busy` names the change being saved for this line
// ('select', 'quantity', 'remove'); `locked` disables every control while any change of the cart is being saved.
export default function CartItem({ line, detail, busy = '', locked = false, onChange, onRemove }) {
  const status = lineStatus(line, detail)
  const { imageUrl, slug, variantLabel } = lineDisplay(line, detail)
  const buyable = status === 'ok' || status === 'atLimit'
  // Added at the price now struck through (a direct promotion started since): the struck price already says so.
  const priceChanged = Number(line.UnitPrice) !== Number(line.CurrentPrice) && Number(line.UnitPrice) !== Number(line.OriginalPrice)
  const stockText = STOCK_TEXT[status]
    ?? (status === 'atLimit' || line.StockQuantity <= LOW_STOCK ? `Còn ${line.StockQuantity} sản phẩm` : 'Còn hàng')
  const image = <StoreImage src={imageUrl} alt="" loading="lazy" decoding="async"
    fallback={<span className="cart-item-noimage">VieTech</span>} />

  return <article className={`cart-item${buyable ? '' : ' is-unavailable'}`} aria-label={line.ProductName}>
    <div className="cart-item-main">
      <label className="cart-check-hit">
        <input type="checkbox" className="cart-check" checked={line.IsSelected} aria-label={`Chọn ${line.ProductName}`}
          disabled={locked || (!line.IsSelected && !buyable)} aria-busy={busy === 'select' || undefined}
          onChange={(event) => onChange({ IsSelected: event.target.checked })} />
      </label>
      {slug
        ? <Link className="cart-item-media" to={productPath(slug)} tabIndex={-1} aria-hidden="true">{image}</Link>
        : <div className="cart-item-media" aria-hidden="true">{image}</div>}
      <div className="cart-item-info">
        <h3 className="cart-item-name">{line.ProductName}</h3>
        <p className="cart-item-variant">{variantLabel}</p>
        <p className="cart-item-price"><Money value={line.CurrentPrice} />
          {Number(line.OriginalPrice) > Number(line.CurrentPrice) && <del className="cart-item-original">
            <span className="sr-only">Giá gốc </span><Money value={line.OriginalPrice} />
          </del>}</p>
        {priceChanged && <p className="cart-item-note">Giá đã thay đổi, lúc thêm vào giỏ là <Money value={line.UnitPrice} />.</p>}
        {line.Quantity > 1 && <p className="cart-item-note">Thành tiền: <Money className="cart-item-subtotal" value={line.LineTotal} /></p>}
        <div className="cart-item-actions">
          {slug && <Link to={productPath(slug)}>Xem chi tiết</Link>}
          <button type="button" disabled={locked} aria-busy={busy === 'remove' || undefined}
            aria-label={`Xóa ${line.ProductName} khỏi giỏ hàng`} onClick={onRemove}>
            {busy === 'remove' ? 'Đang xóa…' : 'Xóa'}
          </button>
        </div>
      </div>
      <div className="cart-item-qty">
        <span className="cart-item-qty-label" aria-hidden="true">Số lượng</span>
        <QuantityStepper value={line.Quantity} max={line.StockQuantity} label={line.ProductName}
          disabled={locked || status === 'soldOut' || status === 'stopped'}
          onChange={(quantity) => onChange({ Quantity: quantity })} />
        <span className={`cart-item-stock${buyable ? '' : ' is-danger'}`}>{stockText}</span>
      </div>
    </div>
    <LineNotice line={line} status={status} disabled={locked} onChange={onChange} />
  </article>
}

function LineNotice({ line, status, disabled, onChange }) {
  if (status === 'ok') return null
  const danger = status !== 'atLimit'
  return <div className={`cart-item-warning${danger ? ' is-danger' : ''}`}>
    <span aria-hidden="true">!</span>
    <p>
      {status === 'atLimit' && 'Số lượng trong kho có hạn. Bạn đã chọn tối đa số lượng hiện có.'}
      {status === 'overStock' && `Chỉ còn ${line.StockQuantity} sản phẩm trong kho. Hãy giảm số lượng để tiếp tục đặt hàng.`}
      {status === 'soldOut' && 'Sản phẩm đã hết hàng. Hãy bỏ chọn hoặc xóa sản phẩm này để tiếp tục đặt hàng.'}
      {status === 'stopped' && 'Sản phẩm không còn được bán. Hãy bỏ chọn hoặc xóa sản phẩm này để tiếp tục đặt hàng.'}
    </p>
    {status === 'overStock' && <button type="button" disabled={disabled}
      onClick={() => onChange({ Quantity: line.StockQuantity })}>Giảm còn {line.StockQuantity}</button>}
  </div>
}
