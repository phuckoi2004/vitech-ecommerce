const paths = {
  history: <><rect x="3" y="4" width="18" height="16" rx="3" /><path d="M9 4v16M13 9h4M13 13h3" /></>,
  new: <><path d="M12 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-6" /><path d="m15 4 5 5M10 14l1-5 7-7 4 4-7 7-5 1Z" /></>,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  expand: <><path d="M10 20H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v4" /><rect x="13" y="13" width="7" height="7" rx="1.5" /><path d="M12 12 8 8m0 4V8h4" /></>,
  collapse: <><path d="M10 20H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v4" /><rect x="13" y="13" width="7" height="7" rx="1.5" /><path d="m8 8 4 4m0-4v4H8" /></>,
  sparkles: <><path d="m12 3 2.6 6.4L21 12l-6.4 2.6L12 21l-2.6-6.4L3 12l6.4-2.6L12 3Z" /><path d="m20 2 .6 1.4L22 4l-1.4.6L20 6l-.6-1.4L18 4l1.4-.6L20 2Z" /></>,
  send: <path d="M12 19V5m-6 6 6-6 6 6" />,
  stop: <rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor" stroke="none" />,
  laptop: <><rect x="4" y="4" width="16" height="12" rx="2" /><path d="m4 16-2 4h20l-2-4M9 20h6" /></>,
  phone: <><rect x="6" y="2" width="12" height="20" rx="3" /><path d="M10 5h4M11 19h2" /></>,
  compare: <><rect x="3" y="5" width="7" height="14" rx="2" /><rect x="14" y="5" width="7" height="14" rx="2" /><path d="M6 9h1m10 6h1" /></>,
  budget: <><rect x="3" y="5" width="18" height="15" rx="3" /><path d="M3 9h18m-6 5h6" /><circle cx="16" cy="14" r=".5" /></>,
  message: <path d="M21 11a8 8 0 0 1-8 8H7l-4 2V11a8 8 0 0 1 18 0Z" />,
  chevron: <path d="m9 5 7 7-7 7" />,
}

export default function AiChatIcon({ name, ...props }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name]}</svg>
}
