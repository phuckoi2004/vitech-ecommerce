import { useId } from 'react'

export default function VariantImageSelection({ images, selected, defaultUrl, onChange, sku, color }) {
  const group = useId()
  function toggle(url, checked) {
    const next = checked ? [...selected, url] : selected.filter((entry) => entry !== url)
    onChange(next, next.includes(defaultUrl) ? defaultUrl : next[0] ?? null)
  }
  return <section className="flex flex-col gap-3 rounded-[14px] border border-admin-border bg-white p-5" aria-label="Ảnh của biến thể">
    <h3 className="m-0 text-[15px] font-semibold">Ảnh của biến thể{sku ? ' ' + sku : ''}{color ? ' · ' + color : ''}</h3>
    <p className="m-0 text-[11px] leading-normal text-admin-muted">Tích chọn những ảnh thuộc biến thể này trong bộ ảnh sản phẩm, rồi chọn một ảnh đại diện.</p>
    {!images.length && <p className="m-0 text-xs text-admin-muted">Tải ảnh từ máy vào bộ ảnh sản phẩm để chọn.</p>}
    <div className="grid grid-cols-3 gap-3">{images.map((image, index) => {
      const chosen = selected.includes(image.ImageUrl)
      return <div key={image.ImageUrl} className={'flex min-w-0 flex-col gap-2 rounded-[10px] border p-2 ' + (chosen ? 'border-admin-blue bg-admin-soft' : 'border-admin-border')}>
        <label className="flex cursor-pointer flex-col gap-2"><img src={image.ImageUrl} alt={'Ảnh để chọn ' + (index + 1)} className="h-24 w-full object-contain" /><span className="flex items-center gap-2 text-xs"><input type="checkbox" aria-label={'Chọn ảnh ' + (index + 1) + ' cho biến thể'} checked={chosen} onChange={(event) => toggle(image.ImageUrl, event.target.checked)} />Ảnh {index + 1}</span></label>
        {chosen && <label className="flex items-center gap-1.5 text-[11px]"><input type="radio" name={group} aria-label={'Ảnh đại diện biến thể ' + (index + 1)} checked={defaultUrl === image.ImageUrl} onChange={() => onChange(selected, image.ImageUrl)} />Ảnh đại diện</label>}
      </div>
    })}</div>
  </section>
}
