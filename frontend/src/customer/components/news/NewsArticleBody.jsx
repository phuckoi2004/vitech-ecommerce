import { useEffect, useMemo } from 'react'
import { richTextToHtml } from '../../../lib/rich-text.js'
import '../../../components/shared/RichText.css'

function prepareContent(value) {
  const template = document.createElement('template')
  template.innerHTML = richTextToHtml(value)
  const headings = []
  let firstHeading = null

  for (let node of [...template.content.children]) {
    const text = node.textContent.trim()
    if (!text) continue
    // The Admin editor also saves section titles as standalone, enlarged bold paragraphs.
    if (node.tagName === 'P' && text.length <= 240 && !node.querySelector('img, br')) {
      const bold = node.querySelector('strong, b')
      const largeText = [...node.querySelectorAll('span')].some(span =>
        Number.parseFloat(span.style.fontSize) >= 18 && span.textContent.trim() === text)
      if (bold?.textContent.trim() === text && largeText) {
        const heading = document.createElement('h2')
        if (node.style.textAlign) heading.style.textAlign = node.style.textAlign
        heading.append(...node.childNodes)
        node.replaceWith(heading)
        node = heading
      }
    }
    if (!/^H[2-4]$/.test(node.tagName)) continue
    const id = `news-section-${headings.length + 1}`
    // Generated anchors are added after sanitization; saved HTML cannot supply IDs or event handlers.
    node.id = id
    node.tabIndex = -1
    firstHeading ??= node
    headings.push({ id, text, level: Number(node.tagName[1]) })
  }

  const intro = document.createElement('div')
  const body = document.createElement('div')
  let inBody = !firstHeading
  for (const node of [...template.content.childNodes]) {
    if (node === firstHeading) inBody = true
    const target = inBody ? body : intro
    target.append(node)
  }
  return { intro: intro.innerHTML, body: body.innerHTML, headings }
}

export default function NewsArticleBody({ value }) {
  const content = useMemo(() => prepareContent(value), [value])
  const hasContents = content.headings.length > 1

  useEffect(() => {
    const id = window.location.hash.slice(1)
    if (content.headings.some(item => item.id === id)) document.getElementById(id)?.scrollIntoView?.()
  }, [content])

  return <div className="news-article-body">
    {content.intro && <div className="vt-rich-text news-article-prose" dangerouslySetInnerHTML={{ __html: content.intro }} />}
    {hasContents && <details className="news-article-toc" open>
      <summary>Mục lục bài viết</summary>
      <nav aria-label="Mục lục bài viết"><ol>
        {content.headings.map(item => <li key={item.id} className={item.level > 2 ? 'is-nested' : undefined}>
          <a href={`#${item.id}`} onClick={() => document.getElementById(item.id)?.focus({ preventScroll: true })}>{item.text}</a>
        </li>)}
      </ol></nav>
    </details>}
    {content.body && <div className="vt-rich-text news-article-prose" dangerouslySetInnerHTML={{ __html: content.body }} />}
  </div>
}
