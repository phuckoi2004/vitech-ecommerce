// Customer site paths. Unknown URLs render the 404 page.
export const HOME_PATH = '/'
export const LOGIN_PATH = '/dang-nhap'
export const REGISTER_PATH = '/dang-ky'
export const FORGOT_PASSWORD_PATH = '/quen-mat-khau'
export const ACCOUNT_PATH = '/tai-khoan'

// Pages linked from the header and the home page.
export const SEARCH_PATH = '/tim-kiem'
export const CART_PATH = '/gio-hang'
export const WISHLIST_PATH = '/yeu-thich'
export const NOTIFICATIONS_PATH = '/thong-bao'
export const NEWS_PATH = '/tin-tuc'
export const CHAT_PATH = '/tu-van'

export const INFO_PATHS = {
  about: '/gioi-thieu',
  contact: '/lien-he',
  stores: '/he-thong-cua-hang',
  buyingGuide: '/huong-dan-mua-hang',
  payment: '/thanh-toan',
  shipping: '/van-chuyen',
  afterSales: '/doi-tra-va-bao-hanh',
  privacy: '/chinh-sach-bao-mat',
  terms: '/dieu-khoan-su-dung',
  returns: '/chinh-sach-doi-tra',
  warranty: '/chinh-sach-bao-hanh',
}

export const productPath = (slug) => `/san-pham/${encodeURIComponent(slug)}`
export const categoryPath = (slug) => `/danh-muc/${encodeURIComponent(slug)}`
export const brandPath = (slug) => `/thuong-hieu/${encodeURIComponent(slug)}`
export const newsPath = (slug) => `${NEWS_PATH}/${encodeURIComponent(slug)}`
