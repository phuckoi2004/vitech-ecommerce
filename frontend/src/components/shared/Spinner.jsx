// Decorative spinner; pair it with visible text or a role="status" container.
export default function Spinner({ className = '' }) {
  return <span className={`inline-block size-4 shrink-0 animate-spin rounded-full border-2 border-current border-r-transparent ${className}`}
    aria-hidden="true" />
}
