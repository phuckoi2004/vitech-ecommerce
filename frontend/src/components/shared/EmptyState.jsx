// Nothing to show yet (empty list, missing page, section not available). `action` is an optional element.
export default function EmptyState({ title, description, action, headingLevel = 2, className = '' }) {
  const Heading = `h${headingLevel}`
  return <section className={`mx-auto flex max-w-md flex-col items-center gap-3 px-4 py-16 text-center font-sans ${className}`}>
    <Heading className="text-xl font-bold text-ink-900">{title}</Heading>
    {description && <p className="text-sm leading-relaxed text-muted-600">{description}</p>}
    {action && <div className="mt-2">{action}</div>}
  </section>
}
