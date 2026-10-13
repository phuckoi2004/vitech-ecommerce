import Button from './Button.jsx'

// A failure the user can read and, when `onRetry` is given, retry. `message` should already be user-facing
// (ApiError.message is Vietnamese and never contains submitted input).
export default function ErrorState({ title = 'Không thể hiển thị nội dung', message, onRetry, retryLabel = 'Thử lại',
  className = '' }) {
  return <section role="alert" className={`mx-auto flex max-w-md flex-col items-center gap-3 px-4 py-12 text-center font-sans ${className}`}>
    <h2 className="text-lg font-bold text-ink-900">{title}</h2>
    {message && <p className="text-sm leading-relaxed text-muted-600">{message}</p>}
    {onRetry && <Button variant="outline" onClick={onRetry}>{retryLabel}</Button>}
  </section>
}
