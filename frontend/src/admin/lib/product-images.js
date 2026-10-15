// Same limits as the backend upload endpoint (existing public bucket policy), for gallery and description images.
export const PRODUCT_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp']
export const PRODUCT_IMAGE_MAX_BYTES = 2 * 1024 * 1024
export const PRODUCT_IMAGE_RULE = 'Chọn ảnh JPG, PNG hoặc WEBP, tối đa 2 MB mỗi ảnh.'

export function isAllowedProductImage(file) {
  return PRODUCT_IMAGE_TYPES.includes(file?.type) && file.size > 0 && file.size <= PRODUCT_IMAGE_MAX_BYTES
}
