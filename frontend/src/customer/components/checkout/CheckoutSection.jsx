// Figma "Section Header": a red step number and the section title, on a white card.
export default function CheckoutSection({ step, title, id, children }) {
  return <section className="checkout-section" aria-labelledby={id}>
    <h2 id={id} className="checkout-section-title"><span className="checkout-step" aria-hidden="true">{step}</span>{title}</h2>
    {children}
  </section>
}
