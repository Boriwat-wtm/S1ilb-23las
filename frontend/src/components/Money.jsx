import { fmtMoney } from '../utils/format'

/**
 * Every amount in the app renders through here, for one reason: the sign.
 *
 * Colour alone cannot carry direction — it fails in greyscale, in print, and
 * for a good share of colour-blind readers — so `+` and `−` are always
 * present, and the colour is a second, redundant channel. The words behind
 * those colours also change per ledger kind (money "in" is income in a
 * cashflow book and new debt in a debt book), which is another reason the
 * colours here mean credit/debit and never good/bad.
 *
 * `display` splits the satang onto a lighter, smaller span. At masthead size
 * two decimals shout as loudly as the baht and are the part nobody reads;
 * de-emphasising them is what makes a big figure look set rather than typed.
 * It is deliberately *not* the default: inside the table every figure shares a
 * column, and mixing sizes there would break the decimal alignment that
 * tabular figures exist to provide.
 */
export default function Money({
  value,
  direction,
  signed = true,
  display = false,
  className = '',
}) {
  const n = Number(value)
  // With no explicit direction this is a balance, so the sign of the number
  // decides how it reads.
  const dir = direction ?? (n > 0 ? 'in' : n < 0 ? 'out' : 'zero')

  let sign = ''
  if (signed && dir === 'in') sign = '+'
  else if (signed && dir === 'out') sign = '−'

  const text = fmtMoney(Math.abs(n))
  const cls = `amount num ${dir} ${className}`.trim()

  if (!display) {
    return (
      <span className={cls}>
        {sign}
        {text}
      </span>
    )
  }

  const dot = text.lastIndexOf('.')
  const baht = dot === -1 ? text : text.slice(0, dot)
  const satang = dot === -1 ? '' : text.slice(dot)

  return (
    <span className={cls}>
      {sign}
      {baht}
      {satang && <span className="amount-satang">{satang}</span>}
    </span>
  )
}
