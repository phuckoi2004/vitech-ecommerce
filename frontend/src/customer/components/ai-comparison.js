export function isComparison(value) {
  return value?.Version === 1 && Array.isArray(value.Products) && value.Products.length >= 2 && value.Products.length <= 3
    && value.Products.every((product) => product && typeof product.ProductName === 'string' && typeof product.Slug === 'string'
      && typeof product.ProductVariantId === 'string' && ['string', 'number'].includes(typeof product.Price)
      && String(product.Price).trim() !== '' && Number.isFinite(Number(product.Price)) && Number(product.Price) >= 0)
    && new Set(value.Products.map((product) => product.ProductVariantId)).size === value.Products.length
    && Array.isArray(value.Rows) && value.Rows.length <= 24 && value.Rows.every((row) => row && typeof row.Label === 'string'
      && Array.isArray(row.Values) && row.Values.length === value.Products.length && row.Values.every((v) => typeof v === 'string'))
}

// Older saved comparisons contain automatic notes unrelated to the customer's question.
// Hide only those fixed notes; keep specific uncertainties and connection conditions.
const legacyNotes = new Set([
  'Giá và tồn kho được ghi nhận tại thời điểm tư vấn; xem trang sản phẩm để kiểm tra lại.',
  'Điểm phù hợp là đánh giá theo tiêu chí của VieTech, không phải kết quả đo hiệu năng.',
  'Một số thông số chưa có dữ liệu; chưa thể kết luận đầy đủ về các tiêu chí đó.',
  'Dung lượng pin không xác định thời lượng sử dụng thực tế.',
  'Không kết luận chất lượng ảnh chỉ từ số MP.',
  'Chưa có kiểm thử phần mềm thực tế; không cam kết chạy mượt Android Studio, trò chơi hoặc ứng dụng cụ thể.',
])

export function comparisonCaveats(value) {
  return Array.isArray(value) ? value.filter((line) => typeof line === 'string' && line.trim()
    && !legacyNotes.has(line.trim())
    && !line.trim().startsWith('Các phiên bản chỉ khác màu sắc có cùng thông số và giá; bảng dùng ')) : []
}

export function comparisonRows(comparison) {
  const showColor = comparison.Needs?.some((need) => /^màu sắc$/i.test(need))
  return comparison.Rows.filter((row) => showColor ||
    !(row.Key === 'color' || /^(?:màu(?: sắc)?|colou?r)$/i.test(row.Label.trim())))
}

export function comparisonDifferences(value) {
  // Old saved snapshots merely joined every column with anonymous sample numbers.
  // Their facts remain visible in the table, omit the repeated paragraph.
  return Array.isArray(value) ? value.filter((line) => typeof line === 'string' &&
    !/mẫu\s+[123]\s*:/i.test(line)) : []
}

export function comparisonValueLines(key, value) {
  if (!['camera', 'front_camera'].includes(key)) return String(value).split(/\r?\n/)
  const parts = String(value).split(/[;；\n]+|,\s*(?=(?:Camera\s+(?:chính|góc|tele)|\d+(?:[.,]\d+)?\s*MP\b))/i)
  const modules = []
  for (const part of parts.map((p) => p.trim()).filter(Boolean)) {
    if (modules.length && !/\d+\s*MP\b/i.test(part)) modules[modules.length - 1] += `, ${part}`
    else modules.push(part)
  }
  return modules
}
