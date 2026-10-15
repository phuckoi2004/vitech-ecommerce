import { useMemo } from 'react'
import { richTextToHtml } from '../../lib/rich-text.js'
import './RichText.css'

// Shows a saved description: legacy plain text becomes paragraphs and HTML passes through the sanitizer first.
export default function RichTextContent({ value, className = '', fallback = null, ...props }) {
  const html = useMemo(() => richTextToHtml(value), [value])
  if (!html) return fallback
  return <div className={`vt-rich-text ${className}`} {...props} dangerouslySetInnerHTML={{ __html: html }} />
}
