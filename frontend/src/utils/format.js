const BKK = 'Asia/Bangkok'

/** Bangkok wall-clock parts for a Date, regardless of the phone's own tz. */
function bangkokParts(date) {
  const fmt = new Intl.DateTimeFormat('en-CA', {
    timeZone: BKK,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  })
  return Object.fromEntries(fmt.formatToParts(date).map((p) => [p.type, p.value]))
}

/**
 * Value for an <input type="datetime-local">, in Bangkok time.
 * The backend reads a naive timestamp as Bangkok wall clock, so whatever this
 * produces can be posted back verbatim — no conversion on either side.
 */
export function toLocalInputValue(input) {
  const d = input ? new Date(input) : new Date()
  if (Number.isNaN(d.getTime())) return ''
  const p = bangkokParts(d)
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`
}

export const nowLocalInputValue = () => toLocalInputValue(new Date())

export function fmtMoney(value) {
  const n = Number(value)
  if (Number.isNaN(n)) return '—'
  return n.toLocaleString('th-TH', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function fmtMoneyShort(value) {
  const n = Number(value)
  if (Number.isNaN(n)) return '—'
  return n.toLocaleString('th-TH', { maximumFractionDigits: 0 })
}

export function fmtDateTime(iso) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('th-TH', {
    timeZone: BKK,
    day: 'numeric',
    month: 'short',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function fmtDateShort(iso) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('th-TH', { timeZone: BKK, day: 'numeric', month: 'short' })
}

export function fmtTime(iso) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleTimeString('th-TH', { timeZone: BKK, hour: '2-digit', minute: '2-digit' })
}

/** "YYYY-MM" for the current Bangkok month. */
export function currentMonth() {
  const p = bangkokParts(new Date())
  return `${p.year}-${p.month}`
}

export function monthLabel(ym) {
  const [y, m] = ym.split('-').map(Number)
  // Noon UTC keeps the month from sliding either way when re-localised.
  const d = new Date(Date.UTC(y, m - 1, 15, 12))
  return d.toLocaleDateString('th-TH', { timeZone: BKK, month: 'long', year: 'numeric' })
}

/** The last `count` months, newest first, as { value, label }. */
export function monthOptions(count = 14) {
  const p = bangkokParts(new Date())
  let year = Number(p.year)
  let month = Number(p.month)
  const out = []
  for (let i = 0; i < count; i += 1) {
    const value = `${year}-${String(month).padStart(2, '0')}`
    out.push({ value, label: monthLabel(value) })
    month -= 1
    if (month === 0) {
      month = 12
      year -= 1
    }
  }
  return out
}

/** Group a flat transaction list into day buckets for the list view. */
export function groupByDay(items) {
  const groups = new Map()
  for (const tx of items) {
    const p = bangkokParts(new Date(tx.occurred_at))
    const key = `${p.year}-${p.month}-${p.day}`
    if (!groups.has(key)) groups.set(key, { key, date: tx.occurred_at, items: [], total: 0 })
    const g = groups.get(key)
    g.items.push(tx)
    g.total += Number(tx.amount)
  }
  return [...groups.values()]
}
