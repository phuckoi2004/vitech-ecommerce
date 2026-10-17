import { useState } from 'react'
import { variantImages } from '../../../lib/product-detail.js'
import StoreImage from '../StoreImage.jsx'
import ProductModal from './ProductModal.jsx'

// Shows the photos of the selected variant; ProductPage remounts it per variant so the main photo resets.
export default function ProductGallery({ product, variant }) {
  const images = variantImages(product, variant?.ProductVariantId)
  const [selectedUrl, setSelectedUrl] = useState(images[0]?.ImageUrl)
  const [zoom, setZoom] = useState(false)
  const selected = images.find((image) => image.ImageUrl === selectedUrl) ?? images[0]
  const fallback = <span className="pd-image-empty">{images.length ? 'Ảnh sản phẩm đang được cập nhật' : 'Chưa có ảnh sản phẩm'}</span>

  return <section className="pd-card pd-gallery" aria-label="Hình ảnh sản phẩm">
    <button className="pd-main-image" type="button" onClick={() => setZoom(true)} disabled={!selected}
      aria-label={`Phóng to ảnh ${product.Name}`} aria-haspopup="dialog">
      <StoreImage src={selected?.ImageUrl} alt={product.Name} decoding="async" fallback={fallback} />
    </button>
    {!!images.length && <div className="pd-thumbnails" role="group" aria-label="Chọn ảnh sản phẩm">
      {images.map((image, index) => <button key={image.ImageUrl} className="pd-thumbnail" type="button"
        aria-label={`Xem ảnh ${index + 1}`} aria-pressed={image.ImageUrl === selected?.ImageUrl}
        onClick={() => setSelectedUrl(image.ImageUrl)}>
        <StoreImage src={image.ImageUrl} alt="" loading="lazy" decoding="async"
          fallback={<span>Ảnh {index + 1}</span>} />
      </button>)}
    </div>}
    <div className="pd-trust">
      <span>✓ Chính hãng VN/A</span><span>✓ {Number(product.WarrantyMonths) > 0
        ? `Bảo hành ${product.WarrantyMonths} tháng` : 'Xem điều kiện bảo hành'}</span><span>✓ Giao nhanh toàn quốc</span>
    </div>
    <ProductModal open={zoom} title={product.Name} onClose={() => setZoom(false)} className="pd-image-modal">
      <div className="pd-zoom-image"><StoreImage src={selected?.ImageUrl} alt={product.Name} fallback={fallback} /></div>
      {images.length > 1 && <div className="pd-thumbnails" role="group" aria-label="Chọn ảnh phóng to">
        {images.map((image, index) => <button key={image.ImageUrl} type="button" className="pd-thumbnail"
          aria-label={`Phóng to ảnh ${index + 1}`} aria-pressed={image.ImageUrl === selected?.ImageUrl}
          onClick={() => setSelectedUrl(image.ImageUrl)}>
          <StoreImage src={image.ImageUrl} alt="" fallback={<span>Ảnh {index + 1}</span>} />
        </button>)}
      </div>}
    </ProductModal>
  </section>
}
