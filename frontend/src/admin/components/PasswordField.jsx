import { useState } from 'react'
import Icon from './Icon.jsx'

export function PasswordRules({ rules }) {
  return <ul className="password-rules" aria-label="Yêu cầu mật khẩu">{rules.map((rule) => <li key={rule.label} className={rule.met ? 'is-met' : ''}><Icon name="check" />{rule.label}</li>)}</ul>
}

export default function PasswordField({ id, label = 'Mật khẩu', hint, ...props }) {
  const [visible, setVisible] = useState(false)
  return <div className="field">
    <label htmlFor={id}>{label}</label>
    <div className="input-wrap"><Icon name="lock" /><input id={id} type={visible ? 'text' : 'password'} aria-describedby={hint ? `${id}-hint` : undefined} {...props} />
      <button className="password-toggle" type="button" aria-label={`${visible ? 'Ẩn' : 'Hiện'} ${label.toLowerCase()}`} aria-pressed={visible} onClick={() => setVisible(!visible)} disabled={props.disabled}><Icon name={visible ? 'hidden' : 'eye'} /></button>
    </div>
    {hint && <p className="field-hint" id={`${id}-hint`}>{hint}</p>}
  </div>
}
