// Labelled form field. Without children it renders an <Input> with the remaining props; with children, the
// control is provided by the caller (it should use the same `id`).

const INPUT_CLASS = 'h-11 w-full rounded-control border bg-white px-3 font-sans text-sm text-ink-900 placeholder:text-muted-400 '
  + 'transition-colors focus:outline-2 focus:outline-offset-0 disabled:cursor-not-allowed disabled:bg-surface-muted'

export function Input({ invalid = false, className = '', ...props }) {
  const state = invalid ? 'border-brand-500 focus:outline-brand-500' : 'border-line focus:border-brand-500 focus:outline-brand-100'
  return <input className={`${INPUT_CLASS} ${state} ${className}`} aria-invalid={invalid || undefined} {...props} />
}

export default function Field({ id, label, hint, error, required = false, className = '', children, ...inputProps }) {
  const hintId = hint ? `${id}-hint` : null
  const errorId = error ? `${id}-error` : null
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined
  return <div className={`flex flex-col gap-1.5 font-sans ${className}`}>
    <label htmlFor={id} className="text-sm font-semibold text-ink-900">
      {label}
      {required && <span className="ml-0.5 text-brand-500" aria-hidden="true">*</span>}
    </label>
    {children ?? <Input id={id} required={required} invalid={Boolean(error)} aria-describedby={describedBy} {...inputProps} />}
    {hint && <p id={hintId} className="text-xs text-muted-600">{hint}</p>}
    {error && <p id={errorId} className="text-xs font-medium text-brand-600">{error}</p>}
  </div>
}
