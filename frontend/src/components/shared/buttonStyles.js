// Class names shared by <Button> and links styled as buttons (Tailwind utilities on the @theme tokens).
const BASE = 'inline-flex items-center justify-center gap-2 rounded-control font-semibold transition-colors '
  + 'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 '
  + 'disabled:cursor-not-allowed disabled:opacity-60'

const VARIANTS = {
  primary: 'bg-brand-500 text-white hover:bg-brand-600',
  outline: 'border border-brand-500 bg-white text-brand-500 hover:bg-brand-50',
  secondary: 'border border-line bg-white text-ink-900 hover:bg-surface-muted',
  ghost: 'bg-transparent text-ink-700 hover:bg-surface-muted',
}

const SIZES = {
  sm: 'h-8 px-3 text-sm',
  md: 'h-10 px-4 text-sm',
  lg: 'h-12 px-6 text-base',
}

export function buttonClassName({ variant = 'primary', size = 'md', className = '' } = {}) {
  return [BASE, VARIANTS[variant] ?? VARIANTS.primary, SIZES[size] ?? SIZES.md, className].filter(Boolean).join(' ')
}
