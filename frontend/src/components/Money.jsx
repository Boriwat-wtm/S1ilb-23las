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
 */
export default function Money({ value, direction, signed = true, className = '' }) {
  const n = Number(value)
  // With no explicit direction this is a balance, so the sign of the number
  // decides how it reads.
  const dir = direction ?? (n > 0 ? 'in' : n < 0 ? 'out' : 'zero')

  let sign = ''
  if (signed && dir === 'in') sign = '+'
  else if (signed && dir === 'out') sign = '−'

  return (
    <span className={`amount num ${dir} ${className}`.trim()}>
      {sign}
      {fmtMoney(Math.abs(n))}
    </span>
  )
}
