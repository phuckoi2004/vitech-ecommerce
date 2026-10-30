import { customerAiText } from './ai-customer-wording.js'

export const compatibilityLabels = {
  compatible: 'Đáp ứng trong điều kiện đã nêu',
  incompatible: 'Không đáp ứng trong điều kiện đang xét',
  requires_adapter: 'Cần cáp hoặc bộ chuyển đổi phù hợp',
  unknown: 'Chưa thể xác nhận',
}

// Basis 'device_type': a port direction the specs do not state was read by device type, never shown as confirmed.
const inferredLabels = {
  compatible: 'Có thể kết nối (suy theo loại thiết bị)',
  requires_adapter: 'Cần cáp hoặc bộ chuyển đổi (suy theo loại thiết bị)',
}

// ModeBasis 'published_max': the display mode was checked against each port's published maximum, not a verified mode.
const publishedLabels = {
  compatible: 'Chạy được theo mức tối đa hãng công bố',
  requires_adapter: 'Cần cáp/bộ chuyển đổi đạt chuẩn (theo mức hãng công bố)',
}

export const compatibilityLabel = (status, basis, modeBasis) => (modeBasis === 'published_max' && publishedLabels[status])
  || (basis === 'device_type' && inferredLabels[status]) || compatibilityLabels[status]

export const compatibilityStrings = (value) => Array.isArray(value) ? value.filter((line) => typeof line === 'string').map(customerAiText) : []

export function isCompatibility(value) {
  return value?.Version === 1 && Object.hasOwn(compatibilityLabels, value.Status)
    && ['laptop_monitor', 'laptop_video_output', 'unsupported'].includes(value.CheckType)
    && Array.isArray(value.Products) && value.Products.length >= 1 && value.Products.length <= 2
    && value.Products.every((product) => product && typeof product.ProductId === 'string'
      && typeof product.ProductName === 'string' && typeof product.Slug === 'string'
      && ['laptop', 'monitor', 'unsupported'].includes(product.Kind))
    && new Set(value.Products.map((product) => `${product.ProductId}/${product.ProductVariantId ?? ''}`)).size === value.Products.length
    && (value.CheckType !== 'laptop_monitor' || value.Products.length === 2
      && value.Products.some((product) => product.Kind === 'laptop') && value.Products.some((product) => product.Kind === 'monitor'))
    && (value.CheckType !== 'laptop_video_output' || value.Products.length === 1 && value.Products[0].Kind === 'laptop')
    && (value.CheckType !== 'unsupported' || value.Status === 'unknown')
    && Array.isArray(value.Criteria) && value.Criteria.length > 0 && value.Criteria.length <= 8
    && value.Criteria.every((criterion) => criterion && typeof criterion.Id === 'string' && typeof criterion.Label === 'string'
      && typeof criterion.Summary === 'string' && Object.hasOwn(compatibilityLabels, criterion.Status))
    && new Set(value.Criteria.map((criterion) => criterion.Id)).size === value.Criteria.length
    && typeof value.Explanation === 'string'
}
