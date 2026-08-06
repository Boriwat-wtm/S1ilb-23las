import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'

import Money from './Money'
import { useLedgers } from '../data/LedgerContext'

export function ShareBadge({ ledger, className = '' }) {
  /* Privacy is the point of this app, so the state is always stated —
     never left to be inferred from an empty space. */
  const shared = ledger.member_count > 1
  return (
    <span className={`share-badge${shared ? ' is-shared' : ''} ${className}`.trim()}>
      <span aria-hidden="true">{shared ? '👥' : '🔒'}</span>
      {shared ? `${ledger.member_count} คน` : 'ส่วนตัว'}
    </span>
  )
}

export default function LedgerSwitcher({ open, onClose }) {
  const { ledgers, currentId, select } = useLedgers()
  const navigate = useNavigate()
  const panelRef = useRef(null)
  const previousFocus = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    previousFocus.current = document.activeElement
    panelRef.current?.querySelector('button, a')?.focus()

    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      previousFocus.current?.focus?.()
    }
  }, [open, onClose])

  if (!open) return null

  const choose = (id) => {
    select(id)
    onClose()
    navigate('/')
  }

  return (
    <div
      className="sheet-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="เลือกสมุด"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="sheet" ref={panelRef}>
        <div className="section-head">
          <h2 className="t-heading">สมุดของคุณ</h2>
          <button type="button" className="btn btn-quiet btn-sm" onClick={onClose}>
            ปิด
          </button>
        </div>

        <ul className="rail-list sheet-list">
          {ledgers.map((l) => (
            <li key={l.id}>
              <button
                type="button"
                className={`rail-item${l.id === currentId ? ' active' : ''}`}
                onClick={() => choose(l.id)}
                aria-current={l.id === currentId ? 'true' : undefined}
              >
                <span aria-hidden="true">{l.emoji || (l.kind === 'debt' ? '📉' : '📘')}</span>
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
          + สร้างสมุดใหม่
        </button>
      </div>
    </div>
  )
}
