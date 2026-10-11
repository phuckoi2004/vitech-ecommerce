import logo from '../../assets/auth/vietech-logo.png'
import robotBag from '../../assets/mascot/robot-bag.webp'
import robotDelivery from '../../assets/mascot/robot-delivery.webp'
import robotHeart from '../../assets/mascot/robot-heart.webp'
import robotShopping from '../../assets/mascot/robot-shopping.webp'
import robotThinking from '../../assets/mascot/robot-thinking.webp'
import './CustomerAuthLayout.css'

// The mascot team: one large robot in the middle, two small ones on each side.
const SIDE_ROBOTS = [
  { src: robotThinking, width: 652, height: 720, place: 'top-left' },
  { src: robotBag, width: 655, height: 720, place: 'bottom-left' },
  { src: robotHeart, width: 536, height: 720, place: 'top-right' },
  { src: robotDelivery, width: 644, height: 720, place: 'bottom-right' },
]

// Two-column frame for the customer auth pages: brand panel (logo, mascot, slogan) and form card.
export default function CustomerAuthLayout({ children }) {
  return <div className="cauth-page">
    <aside className="cauth-brand">
      <div className="cauth-brand-inner">
        <span className="cauth-logo">
          <img src={logo} alt="VieTech" width="2172" height="724" />
        </span>
        <div className="cauth-mascots" aria-hidden="true">
          <img className="cauth-mascot" src={robotShopping} alt="" width="720" height="629" />
          {SIDE_ROBOTS.map((robot) => <img key={robot.place} className={`cauth-mascot-small is-${robot.place}`}
            src={robot.src} alt="" width={robot.width} height={robot.height} />)}
        </div>
        <p className="cauth-slogan">Công nghệ thông minh, mua sắm dễ dàng.</p>
      </div>
    </aside>
    <main className="cauth-main">
      <section className="cauth-card">{children}</section>
    </main>
  </div>
}
