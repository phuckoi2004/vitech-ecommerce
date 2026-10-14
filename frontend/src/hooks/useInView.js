import { useEffect, useState } from 'react'

// [ref, seen]: `seen` turns true once the element comes within `rootMargin` of the viewport and stays true, so a
// section below the fold loads its data only when the visitor scrolls near it. Without IntersectionObserver
// (tests, old browsers) everything counts as seen.
export default function useInView(rootMargin = '320px') {
  const [node, setNode] = useState(null)
  const [seen, setSeen] = useState(() => typeof IntersectionObserver === 'undefined')

  useEffect(() => {
    if (seen || !node) return undefined
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) setSeen(true)
    }, { rootMargin })
    observer.observe(node)
    return () => observer.disconnect()
  }, [node, seen, rootMargin])

  return [setNode, seen]
}
