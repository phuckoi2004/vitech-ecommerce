export function sharedForm(product) {
  return {
    Name: product?.Name ?? '', CategoryId: product?.CategoryId ?? '', BrandId: product?.BrandId ?? '',
    WarrantyMonths: product?.WarrantyMonths ?? 12, Status: product?.Status ?? 'Draft',
    Description: product?.Description ?? '', Specifications: product?.Specifications ? JSON.stringify(product.Specifications, null, 2) : '',
    Images: (product?.Images ?? []).map(({ ImageUrl, IsDefault }) => ({ ImageUrl, IsDefault })),
  }
}

export function sharedBody(form) {
  if (!form.Name.trim()) throw new Error('Tên sản phẩm không được để trống.')
  let specifications = null
  try {
    specifications = form.Specifications.trim() ? JSON.parse(form.Specifications) : null
    if (specifications !== null && (Array.isArray(specifications) || typeof specifications !== 'object')) throw new Error()
  } catch { throw new Error('Thông số kỹ thuật phải là một đối tượng JSON hợp lệ, ví dụ {"RAM":"16GB"}.') }
  return {
    ...form, Name: form.Name.trim(), WarrantyMonths: Number(form.WarrantyMonths),
    Description: form.Description.trim() || null, Specifications: specifications,
    Images: form.Images.map((image) => ({ ...image, ImageUrl: image.ImageUrl.trim() })),
  }
}
