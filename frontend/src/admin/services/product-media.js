import { request } from '../../services/api/client.js'

export function uploadProductImage(token, file) {
  return request('/admin/product-image-uploads', { method: 'POST', accessToken: token, file })
}
