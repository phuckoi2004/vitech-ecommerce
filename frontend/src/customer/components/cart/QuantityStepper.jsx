import { useState } from 'react'

// Figma "Quantity Control": − / value / +. The value can also be typed; it is sent on Enter or when the field loses
// focus, clamped to 1…max. `max` is the current stock; `disabled` locks every part (another change is being saved).
export default function QuantityStepper({ value, max, label, disabled = false, onChange }) {
  const [draft, setDraft] = useState(null)

  function commit() {
    if (draft === null) return
    setDraft(null)
    const typed = Number.parseInt(draft, 10)
    if (!Number.isFinite(typed)) return
    const next = Math.min(Math.max(typed, 1), Math.max(max, 1))
    if (next !== value) onChange(next)
  }

  return <div className="cart-qty" role="group" aria-label={`Số lượng ${label}`}>
    <button type="button" className="cart-qty-button" aria-label={`Giảm số lượng ${label}`}
      disabled={disabled || value <= 1} onClick={() => onChange(Math.min(value - 1, Math.max(max, 1)))}>−</button>
    <input className="cart-qty-input" type="text" inputMode="numeric" pattern="[0-9]*" maxLength={4}
      aria-label={`Số lượng ${label}`} value={draft ?? String(value)} disabled={disabled}
      onChange={(event) => setDraft(event.target.value.replace(/\D/g, ''))}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === 'Enter') { event.preventDefault(); commit() }
        if (event.key === 'Escape') setDraft(null)
      }} />
    <button type="button" className="cart-qty-button" aria-label={`Tăng số lượng ${label}`}
      disabled={disabled || value >= max} onClick={() => onChange(value + 1)}>+</button>
  </div>
}
