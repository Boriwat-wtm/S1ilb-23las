import { useNavigate } from 'react-router-dom'

import Icon from './Icon'
import Money from './Money'
import Sheet from './Sheet'
import { useLedgers } from '../data/LedgerContext'

/**
 * A ledger's own emoji when it has one, otherwise a stroke icon matching the
 * rest of the chrome — never a fallback emoji, which would sit differently
 * from the real ones and make the list look ragged.
 */
export function ledgerGlyph(ledger, size = 18) {
  if (ledger.emoji) {
    return (
      <span className="glyph-emoji" aria-hidden="true">
        {ledger.emoji}
      </span>
    )
  }
  return <Icon name={ledger.kind === 'debt' ? 'trendDown' : 'book'} size={size} />
}

export function ShareBadge({ ledger, className = '' }) {
  /* Privacy is the point of this app, so the state is always stated —
     never left to be inferred from an empty space. */
  const shared = ledger.member_count > 1
  return (
    <span className={`share-badge${shared ? ' is-shared' : ''} ${className}`.trim()}>
      <Icon name={shared ? 'users' : 'lock'} size={12} />
      {shared ? `${ledger.member_count} คน` : 'ส่วนตัว'}
    </span>
  )
}

export default function LedgerSwitcher({ open, onClose }) {
  const { ledgers, currentId, select } = useLedgers()
  const navigate = useNavigate()

  const choose = (id) => {
    select(id)
    onClose()
    navigate('/')
  }

  return (
    <Sheet open={open} onClose={onClose} title="สมุดของคุณ" label="เลือกสมุด">
      <ul className="rail-list sheet-list">
        {ledgers.map((l) => (
          <li key={l.id}>
            <button
              type="button"
              className={`rail-item${l.id === currentId ? ' active' : ''}`}
              onClick={() => choose(l.id)}
              aria-current={l.id === currentId ? 'true' : undefined}
            >
              {ledgerGlyph(l)}
              <span className="rail-item-name">
                <span className="rail-item-title">{l.name}</span>
                <ShareBadge ledger={l} />
              </span>
              <Money
                value={l.totals.balance}
                signed={l.kind !== 'debt'}
                direction={l.kind === 'debt' ? 'out' : undefined}
              />
            </button>
          </li>
        ))}
        {ledgers.length === 0 && <li className="t-dim">ยังไม่มีสมุด</li>}
      </ul>

      <button
        type="button"
        className="btn btn-block"
        onClick={() => {
          onClose()
          navigate('/ledgers/new')
        }}
      >
        <Icon name="plus" size={17} />
        สร้างสมุดใหม่
      </button>
    </Sheet>
  )
}
