export const BRAND_PAGE_SIZE = 8

export function brandFilter(params) {
  const page = Number(params.get('page'))
  return {
    keyword: params.get('keyword')?.trim() ?? '',
    status: ['active', 'hidden'].includes(params.get('status')) ? params.get('status') : '',
    page: Number.isSafeInteger(page) && page > 0 ? page : 1,
  }
}

export function validLogoUrl(value) {
  try {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol) && Boolean(url.hostname) && !url.username && !url.password
  } catch { return false }
}
