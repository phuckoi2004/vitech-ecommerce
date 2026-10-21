import { Link } from 'react-router-dom'

// LinkUrl is https or an internal path starting with "/" (ContentService); anything else is not a link.
export default function BannerLink({ banner, className, children }) {
  const url = banner.LinkUrl ?? ''
  if (url.startsWith('/') && !url.startsWith('//')) return <Link className={className} to={url}>{children}</Link>
  if (url.startsWith('https://')) return <a className={className} href={url}>{children}</a>
  return <div className={className}>{children}</div>
}
