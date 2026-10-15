import { BANNER_STATUSES, safeBannerLink } from '../lib/banners.js'
export { NewsAction as BannerAction, NewsButton as BannerButton } from './NewsUi.jsx'

export function BannerStatus({ active }) {
  return <span className={'inline-block rounded-full px-2 py-[5px] text-[9px] leading-[11px] font-semibold whitespace-nowrap ' + (active ? 'bg-[#16a34a] text-white' : 'border border-admin-border bg-admin-page text-admin-muted')}>{BANNER_STATUSES[active ? 'active' : 'inactive']}</span>
}
export function BannerLink({ value }) {
  const safe = safeBannerLink(value)
  return safe ? <a href={safe} target="_blank" rel="noopener noreferrer" className="break-all hover:text-admin-blue hover:underline">{value}</a> : <span className="break-all">{value || '—'}</span>
}
export function BannerImage({ src, title, large = false, compact = false }) {
  return <div className={'relative grid shrink-0 place-items-center overflow-hidden rounded-md bg-admin-page ' + (large ? 'h-[240px] w-full' : compact ? 'h-[30px] w-[75px]' : 'h-12 w-[120px]')}>
    {src ? <img key={src} src={src} alt={'Banner ' + title} className="absolute inset-0 h-full w-full object-contain" onLoad={(event) => { event.currentTarget.hidden = false; event.currentTarget.nextElementSibling.hidden = true }} onError={(event) => { event.currentTarget.hidden = true; event.currentTarget.nextElementSibling.hidden = false }} /> : null}
    <span hidden={Boolean(src)} className="absolute text-[8px] text-admin-muted">{src ? 'Không tải được ảnh' : 'Chưa có ảnh'}</span>
  </div>
}
