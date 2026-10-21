import { useEffect, useId, useRef, useState } from 'react'
import { ChevronDownIcon } from './icons.jsx'

export default function CatalogSelect({ label, options, value, onChange, disabled }) {
  const id = useId()
  const root = useRef(null)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const selected = options.findIndex(option => option.value === value)

  useEffect(() => {
    if (!open) return undefined
    const outside = event => { if (!root.current?.contains(event.target)) setOpen(false) }
    document.addEventListener('pointerdown', outside)
    return () => document.removeEventListener('pointerdown', outside)
  }, [open])
  useEffect(() => {
    if (open) document.getElementById(`${id}-${active}`)?.scrollIntoView?.({ block: 'nearest' })
  }, [open, active, id])

  function choose(index) {
    onChange(options[index].value)
    setOpen(false)
  }
  function keyDown(event) {
    if (event.key === 'Tab') { setOpen(false); return }
    if (event.key === 'Escape') { event.preventDefault(); setOpen(false); return }
    if (['Enter', ' '].includes(event.key)) {
      event.preventDefault()
      if (open) choose(active)
      else { setActive(Math.max(0, selected)); setOpen(true) }
    } else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
      event.preventDefault()
      const from = open ? active : Math.max(0, selected)
      setActive(event.key === 'Home' ? 0 : event.key === 'End' ? options.length - 1
        : Math.max(0, Math.min(options.length - 1, from + (event.key === 'ArrowDown' ? 1 : -1))))
      setOpen(true)
    }
  }

  return <div className="search-select-control" ref={root}>
    <button type="button" role="combobox" className="search-select-trigger" aria-label={label}
      aria-expanded={open} aria-haspopup="listbox" aria-controls={id} aria-activedescendant={open ? `${id}-${active}` : undefined}
      disabled={disabled} onKeyDown={keyDown} onClick={() => { setActive(Math.max(0, selected)); setOpen(!open) }}>
      <span>{options[selected]?.label || options[0]?.label}</span><ChevronDownIcon className="search-select-chevron" />
    </button>
    {open && <ul id={id} className="search-select-options" role="listbox" aria-label={label}>
      {options.map((option, index) => <li key={option.value} id={`${id}-${index}`} role="option"
        aria-selected={value === option.value} className={index === active ? 'is-active' : undefined}
        onPointerMove={() => setActive(index)} onMouseDown={event => event.preventDefault()} onClick={() => choose(index)}>{option.label}</li>)}
    </ul>}
  </div>
}
