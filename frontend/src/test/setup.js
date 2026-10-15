import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Unmount rendered trees between tests; files running in the Node environment have no DOM to clean.
afterEach(() => {
  if (typeof document !== 'undefined') cleanup()
})

// jsdom does not implement modal dialogs; components open them with showModal().
if (typeof HTMLDialogElement !== 'undefined') {
  HTMLDialogElement.prototype.showModal ??= function showModal() { this.open = true }
  HTMLDialogElement.prototype.close ??= function close() { this.open = false }
}

// jsdom has no layout; the rich text editor (ProseMirror) measures the selection to scroll it into view.
if (typeof Range !== 'undefined') {
  Range.prototype.getClientRects ??= () => []
  Range.prototype.getBoundingClientRect ??= () => new DOMRect()
  document.elementFromPoint ??= () => null
}
