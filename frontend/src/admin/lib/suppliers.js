export const SUPPLIER_PAGE_SIZE = 5

export function supplierFilters(params) {
  const page = Number(params.get('page'))
  return {
    keyword: (params.get('keyword') ?? '').trim().slice(0, 255),
    status: ['active', 'hidden'].includes(params.get('status')) ? params.get('status') : '',
    page: Number.isSafeInteger(page) && page > 0 ? page : 1,
  }
}

function searchText(value) {
  return String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/gi, 'd').toLocaleLowerCase('vi').replace(/\s+/g, ' ').trim()
}

export function filterSuppliers(rows, { keyword, status }) {
  const term = searchText(keyword)
  return rows.filter((row) => (!status || row.IsActive === (status === 'active')) && (!term || [row.SupplierCode, row.Name, row.Email, row.PhoneNumber].some((value) => {
    const text = searchText(value)
    return text.includes(term) || (/^[+\d\s().-]+$/.test(term) && text.replace(/[\s().-]/g, '').includes(term.replace(/[\s().-]/g, '')))
  })))
}

export function supplierBody(form) {
  const fields = [['SupplierCode', 'Mã nhà cung cấp', 50], ['Name', 'Tên nhà cung cấp', 255], ['PhoneNumber', 'Số điện thoại', 20], ['Address', 'Địa chỉ', 500]]
  const body = {}
  for (const [key, label, max] of fields) {
    body[key] = form[key].trim()
    if (!body[key]) throw new Error(label + ' không được để trống.')
    if (body[key].length > max) throw new Error(label + ' vượt quá ' + max + ' ký tự.')
  }
  for (const [key, label, max] of [['Email', 'Email', 255], ['TaxCode', 'Mã số thuế', 20], ['Note', 'Ghi chú', 4000]]) {
    body[key] = form[key].trim() || null
    if (body[key]?.length > max) throw new Error(label + ' vượt quá ' + max + ' ký tự.')
  }
  if (body.Email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(body.Email)) throw new Error('Email nhà cung cấp không hợp lệ.')
  body.IsActive = form.IsActive
  return body
}
