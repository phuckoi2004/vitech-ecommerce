import { useState } from 'react'
import { Link } from 'react-router-dom'
import heartIcon from '../../assets/icons/heart.svg'
import useAuth from '../../auth/useAuth.js'
import { WISHLIST_PATH } from '../routes/paths.js'
import LoginPromptDialog from './LoginPromptDialog.jsx'

// Header wishlist entry. A visitor without any session is asked to sign in or register first; signed-in staff
// still reach the page, which explains that it is for customers.
export default function WishlistLink() {
  const auth = useAuth()
  const [prompt, setPrompt] = useState(false)
  function open(event) {
    if (!auth.sessionReady || auth.session) return
    event.preventDefault()
    setPrompt(true)
  }
  return <>
    <Link className="shop-action" to={WISHLIST_PATH} onClick={open}>
      <span className="shop-action-text"><strong>Yêu thích</strong></span>
      <img className="shop-action-icon" src={heartIcon} alt="" width="24" height="24" />
    </Link>
    <LoginPromptDialog open={prompt} next={WISHLIST_PATH} onClose={() => setPrompt(false)} />
  </>
}
