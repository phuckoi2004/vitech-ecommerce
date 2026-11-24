// Figma "Option/…": a radio card (shipping method, payment method, saved address). The whole card is the label.
export default function OptionCard({ name, value, checked, title, detail, field, onSelect, disabled = false }) {
  return <label className={`checkout-option${checked ? ' is-selected' : ''}${disabled ? ' is-disabled' : ''}`}>
    <input type="radio" className="checkout-radio" name={name} value={value} checked={checked} disabled={disabled} data-field={field}
      onChange={() => onSelect(value)} />
    <span className="checkout-option-copy">
      <span className="checkout-option-title">{title}</span>
      {detail && <span className="checkout-option-detail">{detail}</span>}
    </span>
  </label>
}
