// Like the backend's fold() (app/core/search_text.py): lowercase, no Vietnamese marks, đ → d, single spaces.
export function foldText(text) {
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().replace(/đ/g, 'd').replace(/\s+/g, ' ').trim()
}

// Every word of the keyword appears as a whole word in the text, ignoring case and marks ("dien thoai" in
// "Chọn điện thoại năm 2026"). An empty keyword matches nothing.
export function hasAllWords(text, keyword) {
  const typed = foldText(keyword).split(/[^\p{L}\p{N}]+/u).filter(Boolean)
  const present = new Set(foldText(text).split(/[^\p{L}\p{N}]+/u))
  return typed.length > 0 && typed.every((word) => present.has(word))
}
