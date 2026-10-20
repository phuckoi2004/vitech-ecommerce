// Same limits as the backend upload endpoint (existing public bucket policy), for gallery and description images.
export const PRODUCT_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp']
export const PRODUCT_IMAGE_MAX_BYTES = 2 * 1024 * 1024
export const PRODUCT_IMAGE_RULE = 'Chọn ảnh JPG, PNG hoặc WEBP, tối đa 2 MB mỗi ảnh.'

export function isAllowedProductImage(file) {
  return PRODUCT_IMAGE_TYPES.includes(file?.type) && file.size > 0 && file.size <= PRODUCT_IMAGE_MAX_BYTES
}

// Pasted image addresses, stored in varchar(500) columns. Product photos and brand logos accept http or https like
// the backend; news and banner images (`secureOnly`) must be https. Spaces are encoded by URL parsing.
export const IMAGE_URL_MAX_LENGTH = 500
export function imageUrlFromInput(input, { secureOnly = false } = {}) {
  const value = typeof input === 'string' ? input.trim() : ''
  if (!value) return { error: 'Nhập đường dẫn ảnh.' }
  if (/^data:/i.test(value)) return { error: 'Đây là ảnh nhúng (data:), không phải đường dẫn. Hãy mở ảnh trong tab mới rồi sao chép địa chỉ trên thanh địa chỉ, hoặc tải ảnh về máy rồi chọn ảnh từ máy.' }
  let url
  try { url = new URL(/^[a-z][a-z0-9+.-]*:/i.test(value) ? value : 'https://' + value.replace(/^\/\//, '')) } catch { url = null }
  if (!url || !['http:', 'https:'].includes(url.protocol) || !url.hostname.includes('.') || url.username || url.password) return { error: 'Đường dẫn ảnh không hợp lệ.' }
  if (secureOnly && url.protocol !== 'https:') return { error: 'Đường dẫn ảnh phải bắt đầu bằng https://' }
  if (url.href.length > IMAGE_URL_MAX_LENGTH) return { error: `Đường dẫn ảnh dài tối đa ${IMAGE_URL_MAX_LENGTH} ký tự.` }
  return { url: url.href }
}

// The same photo may be typed with different spelling (host case, encoded characters); compare normalized forms.
export function sameImageUrl(a, b) {
  const normalize = (value) => { try { return new URL(value.trim()).href } catch { return value.trim() } }
  return typeof a === 'string' && typeof b === 'string' && normalize(a) === normalize(b)
}
