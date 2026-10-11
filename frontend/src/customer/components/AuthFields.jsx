import { useState } from 'react'

// Form fields shared by the customer sign-up and sign-in pages (styles in CustomerAuthLayout.css).

export function EyeIcon({ hidden }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {hidden
      ? <path d="m3 3 18 18M10.6 5.1A11 11 0 0 1 12 5c6.5 0 10 7 10 7a19 19 0 0 1-3 4m-2 2c-1.5.7-3.2 1-5 1-6.5 0-10-7-10-7a19 19 0 0 1 5-5m3 3a3 3 0 0 0 4 4" />
      : <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>}
  </svg>
}

export function Field({ id, label, children }) {
  return <div className="cauth-field"><label htmlFor={id}>{label}</label>{children}</div>
}

// `label` is the visible text; `name` (plain text) names the field for the show/hide button.
export function PasswordInput({ id, label, name = 'mật khẩu', ...props }) {
  const [visible, setVisible] = useState(false)
  return <Field id={id} label={label}>
    <div className="cauth-input-wrap">
      <input id={id} className="cauth-input has-toggle" type={visible ? 'text' : 'password'} {...props} />
      <button type="button" className="cauth-toggle" onClick={() => setVisible(!visible)} aria-label={`${visible ? 'Ẩn' : 'Hiện'} ${name}`} aria-pressed={visible} disabled={props.disabled}><EyeIcon hidden={visible} /></button>
    </div>
  </Field>
}
