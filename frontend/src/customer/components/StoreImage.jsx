import { useState } from 'react'

// A failed URL falls back just like a missing image. A different URL is tried normally.
export default function StoreImage({ src, fallback = null, ...props }) {
  const [failedSource, setFailedSource] = useState(null)
  if (!src || failedSource === src) return fallback
  return <img {...props} src={src} onError={() => setFailedSource(src)} />
}
