// Adapt ProductDetailResponse without supplying sample prices, stock or specifications.
export function productVariants(product) {
  return (Array.isArray(product?.Variants) ? product.Variants : [])
    .filter((variant) => variant?.ProductVariantId && variant.IsActive !== false)
}

export const versionLabel = (variant) => variant.Storage?.trim() || variant.VariantName || 'Tiêu chuẩn'
export const colorLabel = (variant) => variant.Color?.trim() || 'Tiêu chuẩn'

export function variantPrice(variant) {
  if (variant?.Price === null || variant?.Price === undefined || variant.Price === '') return null
  const price = Number(variant.Price)
  return Number.isFinite(price) && price >= 0 ? price : null
}

export function canPurchase(variant) {
  return !!variant?.ProductVariantId && variant.IsActive !== false && variantPrice(variant) !== null
    && Number(variant.StockQuantity) > 0
}

export function initialVariant(variants) {
  return variants.find(canPurchase) ?? variants[0] ?? null
}

export function productImages(product) {
  const images = (Array.isArray(product?.Images) ? product.Images : [])
    .filter((image) => typeof image?.ImageUrl === 'string' && image.ImageUrl.trim())
    .sort((a, b) => Number(!!b.IsDefault) - Number(!!a.IsDefault)
      || Number(a.DisplayOrder || 0) - Number(b.DisplayOrder || 0))
  return [...new Map(images.map((image) => [image.ImageUrl, image])).values()]
}

export function specificationText(value, depth = 0) {
  if (value === null || value === undefined || depth > 5) return ''
  if (typeof value === 'boolean') return value ? 'Có' : 'Không'
  if (Array.isArray(value)) return value.map((item) => specificationText(item, depth + 1)).filter(Boolean).join(', ')
  if (typeof value === 'object') return Object.entries(value)
    .map(([name, item]) => [name, specificationText(item, depth + 1)].filter(Boolean).join(': ')).join('; ')
  return String(value)
}

export function productSpecifications(product, variant) {
  const source = product?.Specifications
  const entries = source && typeof source === 'object' && !Array.isArray(source)
    ? Object.entries(source).map(([name, value]) => [name, specificationText(value)]).filter(([, value]) => value)
    : []
  // Memory and color belong to the selected SKU, rather than the common product description.
  for (const [pattern, name, value] of [
    [/^(bộ nhớ|bộ nhớ trong|dung lượng|dung lượng lưu trữ|storage|storage capacity|rom)$/i, 'Bộ nhớ', variant?.Storage],
    [/^(màu sắc|màu|color|colour)$/i, 'Màu sắc', variant?.Color],
  ]) {
    if (!value?.trim()) continue
    const index = entries.findIndex(([key]) => pattern.test(key.trim()))
    if (index >= 0) entries[index] = [entries[index][0], value.trim()]
    else entries.push([name, value.trim()])
  }
  return entries
}

function specificationWords(value) {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/đ/g, 'd')
    .replace(/[^a-z0-9]+/g, ' ').trim()
}

function specificationKey(value) {
  return specificationWords(value.replace(/\([^)]*\)/g, ''))
}

function highlightText(parts) {
  const values = parts.filter(Boolean).filter((value, index, all) =>
    all.findIndex((other) => specificationWords(other) === specificationWords(value)) === index)
  // A combined screen specification may already contain its panel or refresh-rate value.
  return values.filter((value) => !values.some((other) => other !== value
    && ` ${specificationWords(other)} `.includes(` ${specificationWords(value)} `))).join(' · ')
}

// Select meaningful groups independent of JSON key order. All text comes from the existing API fields.
export function productHighlights(product, variant) {
  const source = product?.Specifications
  const entries = source && typeof source === 'object' && !Array.isArray(source) ? Object.entries(source) : []
  const specs = new Map(entries.map(([name, value]) => [specificationKey(name), specificationText(value).trim()]))
  const read = (...names) => names.map((name) => specs.get(specificationKey(name))).find(Boolean) || ''
  const groups = []
  function add(name, parts) {
    const value = highlightText(parts)
    if (value) groups.push([name, value])
  }

  add('Màn hình', [
    read('Màn hình', 'Display', 'Screen', 'Kích thước màn hình', 'Screen size', 'Display size'),
    read('Loại tấm nền', 'Công nghệ màn hình', 'Tấm nền', 'Panel type', 'Display technology'),
    read('Tần số quét', 'Refresh rate', 'Screen refresh rate'),
  ])

  const ram = read('RAM', 'Bộ nhớ RAM', 'Memory RAM')
  add('Hiệu năng', [read('Chip xử lý', 'Chip', 'Bộ xử lý', 'CPU', 'Processor', 'SoC'), ram && `RAM ${ram}`])

  const rear = read('Camera sau', 'Độ phân giải camera sau', 'Rear camera', 'Main camera', 'Back camera')
  const front = read('Camera trước', 'Độ phân giải camera trước', 'Front camera', 'Selfie camera')
  add('Camera', rear || front ? [rear && `Sau ${rear}`, front && `Trước ${front}`] : [read('Camera', 'Webcam')])

  add('Bộ nhớ', [variant?.Storage?.trim() || read('Bộ nhớ trong', 'Bộ nhớ', 'Dung lượng lưu trữ', 'Storage',
    'Storage capacity', 'ROM', 'Ổ cứng', 'SSD', 'HDD')])

  const charging = read('Công suất sạc hỗ trợ tối đa', 'Công suất sạc', 'Sạc nhanh', 'Charging power', 'Fast charging', 'Charging')
  add('Pin và sạc', [read('Dung lượng pin', 'Pin', 'Battery capacity', 'Battery'), charging && `Sạc ${charging}`])
  return groups
}
