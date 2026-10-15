import DOMPurify from 'dompurify'

// Product descriptions are stored in Products.Description (TEXT) either as legacy plain text or as HTML produced by
// the admin rich text editor. Every value is sanitized with this allowlist before it is shown or saved.
// h2–h4 are no longer produced by the editor but stay allowed so descriptions saved with them still display.
const ALLOWED_TAGS = ['p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'span', 'h2', 'h3', 'h4', 'ul', 'ol', 'li', 'a', 'blockquote', 'img']
const ALLOWED_ATTR = ['href', 'target', 'rel', 'style', 'src', 'alt', 'title']
const ALIGNABLE = new Set(['P', 'H2', 'H3', 'H4', 'LI'])
const SAFE_URI = /^(?:(?:https?|mailto|tel):|\/(?!\/)|#)/i
const IMAGE_SOURCE = /^(?:https?:\/\/|\/(?!\/))/i
const FONT_SIZE = /^(\d{1,2}(?:\.\d+)?)px$/i
const FONT_FAMILY = /^[\p{L}\d\s"',-]{1,120}$/u
const HTML_TAG = /<\/?(?:p|br|h[1-6]|ul|ol|li|strong|b|em|i|u|s|a|blockquote|div|span|img)\b[^>]*>/i
const BLOCK_TAG = /<(?:p|h[1-6]|ul|ol|li|blockquote|div)\b/i
export const MIN_FONT_SIZE = 10
export const MAX_FONT_SIZE = 48

// Only alignment on blocks and font size/family on text spans survive; other CSS could restyle or overlay the page.
function allowedStyle(nodeName, css) {
  const kept = []
  for (const declaration of css.split(';')) {
    const separator = declaration.indexOf(':')
    if (separator < 0) continue
    const name = declaration.slice(0, separator).trim().toLowerCase(), value = declaration.slice(separator + 1).trim()
    if (name === 'text-align' && ALIGNABLE.has(nodeName) && /^(?:left|center|right|justify)$/i.test(value)) kept.push(`text-align: ${value.toLowerCase()}`)
    if (nodeName !== 'SPAN') continue
    const size = FONT_SIZE.exec(value)
    if (name === 'font-size' && size && Number(size[1]) >= MIN_FONT_SIZE && Number(size[1]) <= MAX_FONT_SIZE) kept.push(`font-size: ${value.toLowerCase()}`)
    if (name === 'font-family' && FONT_FAMILY.test(value)) kept.push(`font-family: ${value}`)
  }
  return kept.join('; ')
}

const purifier = typeof window === 'undefined' ? null : DOMPurify(window)

if (purifier?.isSupported) {
  purifier.addHook('uponSanitizeAttribute', (node, data) => {
    if (data.attrName !== 'style') return
    data.attrValue = allowedStyle(node.nodeName, data.attrValue)
    if (!data.attrValue) data.keepAttr = false
  })
  purifier.addHook('afterSanitizeAttributes', (node) => {
    if (node.nodeName === 'IMG') {
      // DOMPurify accepts data: images by default; descriptions only reference uploaded or web images.
      if (!IMAGE_SOURCE.test(node.getAttribute('src') ?? '')) node.removeAttribute('src')
      node.setAttribute('loading', 'lazy')
      node.setAttribute('decoding', 'async')
      return
    }
    if (node.nodeName !== 'A') return
    const href = node.getAttribute('href')
    if (href && /^https?:/i.test(href)) {
      node.setAttribute('target', '_blank')
      node.setAttribute('rel', 'noopener noreferrer nofollow')
    } else {
      node.removeAttribute('target')
      node.removeAttribute('rel')
    }
  })
}

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char])
}

export function isRichTextHtml(value) {
  return typeof value === 'string' && HTML_TAG.test(value)
}

function paragraphs(text, escape) {
  return text.replace(/\r\n?/g, '\n').trim().split(/\n\s*\n/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean)
    .map((paragraph) => `<p>${(escape ? escapeHtml(paragraph) : paragraph).replace(/\n/g, '<br>')}</p>`)
    .join('')
}

// Legacy descriptions: blank lines separate paragraphs and single line breaks stay inside a paragraph.
export function plainTextToHtml(text) {
  return typeof text === 'string' ? paragraphs(text, true) : ''
}

// Text from the former textarea may hold inline tags such as <b> but no blocks; keep its line structure too.
function withParagraphs(html) {
  return BLOCK_TAG.test(html) || !html.includes('\n') ? html : paragraphs(html, false)
}

export function sanitizeRichText(html) {
  if (typeof html !== 'string' || !html.trim()) return ''
  if (!purifier?.isSupported) return plainTextToHtml(html.replace(/<[^>]*>/g, ' '))
  return purifier.sanitize(html, { ALLOWED_TAGS, ALLOWED_ATTR, ALLOWED_URI_REGEXP: SAFE_URI, ALLOW_DATA_ATTR: false })
}

function hasContent(html) {
  return /<img\b/i.test(html) || html.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').trim() !== ''
}

// Blank paragraphs between blocks are intentional spacing; the editor's trailing empty paragraph is not.
const EDGE_EMPTY_PARAGRAPHS = /^(?:\s*<p[^>]*>(?:\s|&nbsp;|<br>)*<\/p>)+|(?:<p[^>]*>(?:\s|&nbsp;|<br>)*<\/p>\s*)+$/g

function cleanHtml(value) {
  const html = sanitizeRichText(withParagraphs(value))
    .replace(/<img(?![^>]*\ssrc=)[^>]*>/gi, '')
    .replace(EDGE_EMPTY_PARAGRAPHS, '').trim()
  return hasContent(html) ? html : ''
}

// Safe HTML for display and for loading into the editor, whichever format the description was saved in.
export function richTextToHtml(value) {
  if (typeof value !== 'string' || !value.trim()) return ''
  return isRichTextHtml(value) ? cleanHtml(value) : plainTextToHtml(value)
}

// Value sent to the API: sanitized HTML, the untouched legacy plain text, or null when nothing was entered.
export function normalizeRichText(value) {
  if (typeof value !== 'string' || !value.trim()) return null
  if (!isRichTextHtml(value)) return value.trim()
  return cleanHtml(value) || null
}

const HEADING_FONT_SIZES = { H2: '20px', H3: '16px', H4: '14px' }

// The editor no longer has headings: a saved h2–h4 opens as a bold paragraph of a similar size, so editing an older
// description keeps its look instead of shrinking the heading to body text.
export function headingsToParagraphs(html) {
  if (typeof document === 'undefined' || !/<h[2-4]\b/i.test(html)) return html
  const template = document.createElement('template')
  template.innerHTML = html
  for (const heading of template.content.querySelectorAll('h2, h3, h4')) {
    const paragraph = document.createElement('p'), strong = document.createElement('strong'), span = document.createElement('span')
    if (heading.style.textAlign) paragraph.style.textAlign = heading.style.textAlign
    span.style.fontSize = HEADING_FONT_SIZES[heading.nodeName]
    span.append(...heading.childNodes)
    strong.append(span)
    paragraph.append(strong)
    heading.replaceWith(paragraph)
  }
  return template.innerHTML
}

// Links typed by an administrator: web, e-mail, phone or site-relative addresses only.
export function normalizeLinkUrl(input) {
  const value = typeof input === 'string' ? input.trim() : ''
  if (!value || /\s/.test(value)) return null
  if (/^\/(?!\/)/.test(value) || /^(?:mailto|tel):\S+$/i.test(value)) return value
  if (/^[a-z][a-z0-9+.-]*:(?!\d)/i.test(value) && !/^https?:\/\//i.test(value)) return null
  try {
    const url = new URL(/^https?:\/\//i.test(value) ? value : `https://${value}`)
    return url.hostname.includes('.') || url.hostname === 'localhost' ? url.href : null
  } catch { return null }
}

// Image addresses: web or site-relative only (no data: URLs, which would bloat the description).
export function normalizeImageUrl(input) {
  const url = normalizeLinkUrl(input)
  return url && IMAGE_SOURCE.test(url) ? url : null
}
