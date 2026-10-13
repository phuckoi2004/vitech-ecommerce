import Spinner from './Spinner.jsx'

// Announced loading message. `fullScreen` centers it in the viewport (used before a layout exists).
export default function LoadingState({ label = 'Đang tải…', fullScreen = false, className = '' }) {
  return <div role="status" className={`flex items-center justify-center gap-3 px-4 py-12 font-sans text-sm text-muted-600 ${fullScreen ? 'min-h-dvh' : ''} ${className}`}>
    <Spinner className="text-brand-500" />
    <span>{label}</span>
  </div>
}
