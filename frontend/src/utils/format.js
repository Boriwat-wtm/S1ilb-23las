const BKK = 'Asia/Bangkok'

/** Bangkok wall-clock parts for a Date, whatever the phone's own timezone is. */
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
 * Value for <input type="datetime-local">, in Bangkok time.
 * The backend reads a naive timestamp as Bangkok wall clock, so this can be
 * posted back verbatim — no conversion on either side, nothing to get
 * backwards.
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

export function fmtMoneyRound(value) {
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

export function fmtDayFull(iso) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('th-TH', {
    timeZone: BKK,
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  })
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

/** "YYYY-MM-DD" bucket key in Bangkok time. */
export function dayKey(iso) {
  const p = bangkokParts(new Date(iso))
  return `${p.year}-${p.month}-${p.day}`
}

export function monthLabel(ym) {
  const [y, m] = ym.split('-').map(Number)
  // Noon UTC keeps the month from sliding when re-localised.
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

// --- ledger vocabulary -----------------------------------------------------
/**
 * The same in/out pair means different things in the two ledger kinds, and
 * every screen needs the right words. Centralised so a debt book never says
 * "รายรับ" for money it just borrowed.
 */
export function ledgerWords(kind) {
  if (kind === 'debt') {
    return {
      in: 'หนี้เพิ่ม',
      out: 'จ่ายคืน',
      balance: 'ยอดหนี้คงค้าง',
      periodBalance: 'เปลี่ยนแปลงเดือนนี้',
      entry: 'รายการหนี้',
      // A debt balance going down is the good direction.
      balanceIsDebt: true,
    }
  }
  return {
    in: 'รายรับ',
    out: 'รายจ่าย',
    balance: 'คงเหลือ',
    periodBalance: 'คงเหลือเดือนนี้',
    entry: 'รายการ',
    balanceIsDebt: false,
  }
}

/** Signed effect of an entry on the ledger balance. */
export const entryEffect = (entry) =>
  (entry.direction === 'in' ? 1 : -1) * Number(entry.amount)

/**
 * Cumulative balance as of each row, within the current filter.
 *
 * Rows arrive newest-first and `filterBalance` is the exact server-side total
 * for the whole filter, so the newest row sits at that total and each older
 * row is the previous one minus the newer row's effect. That makes the column
 * correct for any prefix of the list — which matters, because pagination means
 * we usually only hold a prefix.
 */
export function withRunningBalance(entries, filterBalance) {
  let running = Number(filterBalance)
  return entries.map((entry) => {
    const row = { ...entry, running }
    running -= entryEffect(entry)
    return row
  })
}
