export function StarIcon({ filled = true }) {
  return <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"
    fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round">
    <path d="m12 3 2.8 5.7 6.3.9-4.5 4.4 1.1 6.2-5.7-3-5.7 3 1.1-6.2L2.9 9.6l6.3-.9Z" />
  </svg>
}

export default function ReviewStars({ rating, label = `${rating} trên 5 sao` }) {
  return <span className="pr-stars" role="img" aria-label={label}>
    {[1, 2, 3, 4, 5].map((star) => <span className="pr-star" key={star} aria-hidden="true">
      <StarIcon filled={false} />
      <span className="pr-star-fill" style={{ width: `${Math.max(0, Math.min(1, rating - star + 1)) * 100}%` }}><StarIcon /></span>
    </span>)}
  </span>
}
