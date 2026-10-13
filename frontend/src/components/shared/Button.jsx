import { buttonClassName } from './buttonStyles.js'
import Spinner from './Spinner.jsx'

// Variants: primary, outline, secondary, ghost. Sizes: sm, md, lg. `loading` disables the button and shows a spinner.
export default function Button({ variant = 'primary', size = 'md', loading = false, disabled = false, type = 'button',
  className = '', children, ...props }) {
  return <button type={type} className={buttonClassName({ variant, size, className })} disabled={disabled || loading}
    aria-busy={loading || undefined} {...props}>
    {loading && <Spinner />}
    {children}
  </button>
}
