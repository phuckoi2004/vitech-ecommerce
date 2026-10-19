import { addressLine, RECEIVER_LIMITS } from './checkoutForm.js'
import OptionCard from './OptionCard.jsx'

// Figma "Delivery Address" with its "Thay đổi" link: the chosen address-book entry, the list to pick another one,
// or a receiver typed for this order only (also the only choice when the address book is empty or did not load).
// Nothing is saved to the address book from here. `addresses` is a useApiData result of GET /users/me/addresses.
export default function AddressPicker({ addresses, mode, addressId, receiver, choosing, errors, onToggle, onPick, onReceiverChange }) {
  const saved = addresses.data ?? []
  const current = saved.find((address) => address.AddressId === addressId)

  return <div className="checkout-address">
    <div className="checkout-subhead">
      <h3>Địa chỉ giao hàng</h3>
      {saved.length > 0 && <button type="button" className="checkout-link" aria-expanded={choosing} data-field="address"
        onClick={onToggle}>{choosing ? 'Đóng' : 'Thay đổi'}</button>}
    </div>
    {addresses.loading ? <p className="checkout-muted" role="status">Đang tải sổ địa chỉ…</p> : <>
      {addresses.error && <p className="checkout-inline-error" role="alert">
        Không tải được sổ địa chỉ. {addresses.error}{' '}
        <button type="button" onClick={addresses.reload}>Thử lại</button>
      </p>}
      {choosing ? <fieldset className="checkout-options is-stacked">
        <legend className="sr-only">Chọn địa chỉ nhận hàng</legend>
        {saved.map((address) => <OptionCard key={address.AddressId} name="checkout-address" value={address.AddressId}
          checked={mode === 'saved' && address.AddressId === addressId} onSelect={onPick}
          title={<>{address.ReceiverName} • {address.ReceiverPhone}{address.IsDefault && <span className="checkout-badge">Mặc định</span>}</>}
          detail={addressLine(address)} />)}
        <OptionCard name="checkout-address" value="new" checked={mode === 'new'} onSelect={onPick}
          title="Giao đến địa chỉ khác" detail="Nhập người nhận và địa chỉ chỉ dùng cho đơn hàng này." />
      </fieldset>
        : mode === 'saved' && current ? <div className="checkout-address-card">
          <p className="checkout-address-name">{current.ReceiverName} • {current.ReceiverPhone}</p>
          <p>{addressLine(current)}</p>
        </div>
          : mode === 'new' ? <ReceiverForm receiver={receiver} errors={errors} onChange={onReceiverChange} /> : null}
      {errors.address && <p className="checkout-error">{errors.address}</p>}
    </>}
  </div>
}

function ReceiverForm({ receiver, errors, onChange }) {
  const field = (name, label, props) => <TextField name={name} label={label} value={receiver[name]} error={errors[name]}
    onChange={onChange} {...props} />
  return <div className="checkout-fields">
    {field('ReceiverName', 'Họ và tên người nhận', { autoComplete: 'name' })}
    {field('ReceiverPhone', 'Số điện thoại', { type: 'tel', inputMode: 'tel', autoComplete: 'tel', placeholder: 'VD: 0912345678' })}
    {field('Province', 'Tỉnh/Thành phố', { autoComplete: 'address-level1', placeholder: 'VD: Hà Nội' })}
    {field('Ward', 'Phường/Xã', { autoComplete: 'address-level2', placeholder: 'VD: Phường Cầu Giấy' })}
    {field('DetailAddress', 'Địa chỉ chi tiết', { autoComplete: 'street-address', placeholder: 'Số nhà, tên đường', wide: true })}
  </div>
}

function TextField({ name, label, value, error, onChange, wide = false, ...props }) {
  const id = `checkout-${name}`
  return <div className={`checkout-field${wide ? ' is-wide' : ''}`}>
    <label htmlFor={id}>{label}<span className="checkout-required" aria-hidden="true"> *</span></label>
    <input id={id} name={name} data-field={name} value={value} maxLength={RECEIVER_LIMITS[name]} aria-required="true"
      aria-invalid={error ? true : undefined} aria-describedby={error ? `${id}-error` : undefined}
      onChange={(event) => onChange(name, event.target.value)} {...props} />
    {error && <p id={`${id}-error`} className="checkout-error">{error}</p>}
  </div>
}
