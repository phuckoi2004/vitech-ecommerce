import { useEffect, useEffectEvent, useState } from 'react'
import { useLocation, useNavigationType } from 'react-router-dom'

// Draft fields stay responsive while URL-backed filters apply after typing pauses.
// Navigation resets the draft; automatic page clamping preserves ongoing input.
export default function useAutoFilters(values, onApply, { validate = () => true } = {}) {
  const location = useLocation()
  const navigation = useNavigationType()
  const source = JSON.stringify(values)
  const sourceKey = location.pathname + ':' + source
  const [state, setState] = useState(() => ({ sourceKey, locationKey: location.key, values }))
  const [composing, setComposing] = useState(false)
  if (state.sourceKey !== sourceKey || state.locationKey !== location.key) {
    const preserve = state.sourceKey === sourceKey && navigation === 'REPLACE'
    setState({ sourceKey, locationKey: location.key, values: preserve ? state.values : values })
  }
  const draft = state.values
  const normalized = Object.fromEntries(Object.entries(draft).map(([key, value]) => [key, typeof value === 'string' ? value.trim() : value]))
  const pending = JSON.stringify(normalized)
  const valid = validate(normalized)
  const applyPending = useEffectEvent(() => onApply(normalized))

  useEffect(() => {
    if (composing || !valid || pending === source) return
    const timer = window.setTimeout(() => applyPending(), 400)
    return () => window.clearTimeout(timer)
  }, [sourceKey, location.key, source, pending, composing, valid])

  function setDraft(next) {
    setState((previous) => ({ ...previous, values: typeof next === 'function' ? next(previous.values) : next }))
  }
  return {
    draft, setDraft,
    formProps: {
      onCompositionStart: () => setComposing(true),
      onCompositionEnd: () => setComposing(false),
      onSubmit: (event) => {
        event.preventDefault()
        if (!composing && !event.nativeEvent?.isComposing && valid && pending !== source) onApply(normalized)
      },
    },
  }
}
