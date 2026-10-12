import { useRef } from 'react'

// Six one-digit boxes for an emailed code. Typing moves forward, Backspace moves back,
// and pasting (or the phone's one-time-code suggestion) fills every box.
export default function OtpInput({ value, onChange, length = 6, disabled = false, label = 'Mã OTP', autoFocus = false }) {
  const boxes = useRef([])
  // An empty box is stored as a space so the digits after it keep their position.
  const digits = Array.from({ length }, (_, index) => (value[index] ?? '').trim())

  function emit(next) {
    onChange(next.map((digit) => digit || ' ').join('').trimEnd())
  }

  function focus(index) {
    boxes.current[Math.max(0, Math.min(length - 1, index))]?.focus()
  }

  function fill(index, text) {
    const incoming = text.replace(/\D/g, '')
    if (!incoming) return
    const next = digits.slice()
    for (let offset = 0; offset < incoming.length && index + offset < length; offset += 1) next[index + offset] = incoming[offset]
    emit(next)
    focus(index + incoming.length)
  }

  function keyDown(index, event) {
    if (event.key === 'Backspace' && !digits[index] && index > 0) {
      event.preventDefault()
      const next = digits.slice()
      next[index - 1] = ''
      emit(next)
      focus(index - 1)
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault()
      focus(index - 1)
    } else if (event.key === 'ArrowRight') {
      event.preventDefault()
      focus(index + 1)
    }
  }

  function change(index, event) {
    const text = event.target.value
    if (!text) {
      const next = digits.slice()
      next[index] = ''
      emit(next)
      return
    }
    // Typing over a filled box gives two characters: keep only the new one. Longer text is an
    // autofilled or pasted code and fills the following boxes.
    fill(index, text.length === 2 && digits[index] ? text.replace(digits[index], '') : text)
  }

  return <div className="cauth-otp" role="group" aria-label={label}>
    {digits.map((digit, index) => <input key={index} ref={(element) => { boxes.current[index] = element }}
      className="cauth-otp-box" type="text" inputMode="numeric" pattern="[0-9]*" maxLength={length}
      autoComplete={index === 0 ? 'one-time-code' : 'off'} autoFocus={autoFocus && index === 0}
      placeholder="•" value={digit} disabled={disabled} aria-label={`Chữ số thứ ${index + 1}`}
      onChange={(event) => change(index, event)} onKeyDown={(event) => keyDown(index, event)}
      onPaste={(event) => { event.preventDefault(); fill(index, event.clipboardData.getData('text')) }}
      onFocus={(event) => event.target.select()} />)}
  </div>
}
