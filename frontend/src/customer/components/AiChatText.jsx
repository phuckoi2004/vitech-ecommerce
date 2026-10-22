// A small, text-only Markdown subset. Model content never becomes HTML or a link.
function inline(text) {
  return text.split(/(\*\*[^*\n]+\*\*|__[^_\n]+__|`[^`\n]+`|\*[^*\n]+\*)/g).map((part, index) => {
    if ((part.startsWith('**') && part.endsWith('**') || part.startsWith('__') && part.endsWith('__')) && part.length > 4)
      return <strong key={index}>{part.slice(2, -2)}</strong>
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2)
      return <code key={index}>{part.slice(1, -1)}</code>
    if (part.startsWith('*') && part.endsWith('*') && part.length > 2) return <em key={index}>{part.slice(1, -1)}</em>
    return part
  })
}

export default function AiChatText({ content }) {
  const lines = (content ?? '').replace(/\\r\\n|\\n|\\r/g, '\n').replace(/\r\n?/g, '\n').split('\n')
  const blocks = []
  let current
  function append(kind, text, start) {
    if (!current || current.kind !== kind || kind === 'heading') {
      current = { kind, lines: [], start }
      blocks.push(current)
    }
    current.lines.push(text)
  }
  for (const line of lines) {
    const text = line.trim()
    if (!text) { current = null; continue }
    const heading = text.match(/^#{1,6}\s+(.+?)\s*#*$/)
    const bullet = text.match(/^[-*•]\s+(.+)/)
    const numbered = text.match(/^(\d{1,2})[.)]\s+(.+)/)
    if (heading) append('heading', heading[1])
    else if (bullet) append('ul', bullet[1])
    else if (numbered) append('ol', numbered[2], Number(numbered[1]))
    else if (/^\S.{0,65}:$/.test(text) && current?.kind !== 'p') append('heading', text.slice(0, -1))
    else if (/^\s{2,}/.test(line) && ['ul', 'ol'].includes(current?.kind)) current.lines[current.lines.length - 1] += '\n' + text
    else append('p', line)
  }
  return <div className="ai-chat-text">{blocks.map((block, index) => {
    if (block.kind === 'heading') return <h4 key={index}>{inline(block.lines[0])}</h4>
    if (block.kind === 'ul' || block.kind === 'ol') {
      const List = block.kind
      return <List key={index} start={block.kind === 'ol' && block.start !== 1 ? block.start : undefined}>
        {block.lines.map((line, item) => <li key={item}>{inline(line)}</li>)}
      </List>
    }
    return <p key={index}>{inline(block.lines.join('\n'))}</p>
  })}</div>
}
