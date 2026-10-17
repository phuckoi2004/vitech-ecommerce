import { normalizeRichText } from '../../lib/rich-text.js'
import { specificationText } from '../../lib/product-detail.js'

const escapeHtml = (text) => text.replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char])

// Specifications stay name/value pairs in the API (the storefront builds its table and highlights from them);
// administrators edit them in the description editor, one "Tên: Giá trị" line each.
export const SPECIFICATION_EDITOR = {
  allowImages: false,
  placeholder: 'Mỗi dòng một thông số, ví dụ RAM: 12GB',
  emptyText: 'Chưa có thông số kỹ thuật.',
  toolbarLabel: 'Định dạng thông số kỹ thuật',
  hint: 'Mỗi dòng một thông số theo dạng Tên: Giá trị, ví dụ Chip xử lý: Exynos 2600. Thông số được hiển thị cho khách thành bảng nên định dạng chữ không được lưu lại.',
  readOnlyHint: 'Thông số kỹ thuật dùng chung cho các biến thể của sản phẩm.',
}

export function specificationEntries(specifications) {
  if (!specifications || typeof specifications !== 'object' || Array.isArray(specifications)) return []
  return Object.entries(specifications).map(([name, value]) => [name, specificationText(value)]).filter(([, value]) => value)
}

export function specificationsToHtml(specifications) {
  return specificationEntries(specifications).map(([name, value]) => `<p>${escapeHtml(name)}: ${escapeHtml(value)}</p>`).join('')
}

// Every paragraph, list item or line break of the editor HTML is one line; typed bullets are ignored.
function specificationLines(html) {
  if (typeof html !== 'string' || !html.trim()) return []
  const template = document.createElement('template')
  template.innerHTML = html
  for (const lineBreak of template.content.querySelectorAll('br')) lineBreak.replaceWith('\n')
  for (const block of template.content.querySelectorAll('p, li, div, h1, h2, h3, h4, h5, h6, blockquote')) block.append('\n')
  return template.content.textContent.split('\n').map((line) => line.replace(/\s+/g, ' ').replace(/^[-•*+]\s+/, '').trim()).filter(Boolean)
}

export function parseSpecifications(html) {
  const result = {}, names = new Set()
  for (const line of specificationLines(html)) {
    const at = line.indexOf(':')
    const name = at > 0 ? line.slice(0, at).trim() : '', value = at > 0 ? line.slice(at + 1).trim() : ''
    if (!name || !value) throw new Error(`Thông số kỹ thuật: dòng “${line}” chưa đúng dạng Tên: Giá trị, ví dụ RAM: 12GB.`)
    const key = name.toLocaleLowerCase('vi')
    if (names.has(key)) throw new Error(`Thông số kỹ thuật: “${name}” được nhập hai lần.`)
    names.add(key)
    result[name] = value
  }
  return Object.keys(result).length ? result : null
}

export function sharedForm(product) {
  return {
    Name: product?.Name ?? '', CategoryId: product?.CategoryId ?? '', BrandId: product?.BrandId ?? '',
    WarrantyMonths: product?.WarrantyMonths ?? 12, Status: product?.Status ?? 'Draft',
    Description: product?.Description ?? '', Specifications: specificationsToHtml(product?.Specifications),
    Images: (product?.Images ?? []).map(({ ImageUrl, IsDefault }) => ({ ImageUrl, IsDefault })),
  }
}

export function sharedBody(form) {
  if (!form.Name.trim()) throw new Error('Tên sản phẩm không được để trống.')
  return {
    ...form, Name: form.Name.trim(), WarrantyMonths: Number(form.WarrantyMonths),
    // Editor HTML is sanitized again before saving; an untouched legacy plain-text description is kept as it was.
    Description: normalizeRichText(form.Description), Specifications: parseSpecifications(form.Specifications),
    Images: form.Images.map((image) => ({ ...image, ImageUrl: image.ImageUrl.trim() })),
  }
}
