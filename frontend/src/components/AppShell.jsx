import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'

import LedgerSwitcher, { ShareBadge } from './LedgerSwitcher'
import Money from './Money'
import { useAuth } from '../auth/AuthContext'
import { useLedgers } from '../data/LedgerContext'

/**
 * Mobile gets a header plus a bottom tab bar; from 900px the tab bar is
 * replaced by a persistent ledger rail. That is a recomposition, not a
 * collapse: on a wide screen the most useful thing to keep on screen is the
 * list of books and their balances, which is precisely what does not fit on a
 * phone.
 */
export default function AppShell() {
  const { user, logout } = useAuth()
  const { ledgers, current, currentId, select } = useLedgers()
  const [switcherOpen, setSwitcherOpen] = useState(false)
  const navigate = useNavigate()

  const tab = ({ isActive }) => `tab${isActive ? ' active' : ''}`
  const railLink = ({ isActive }) => (isActive ? 'active' : undefined)

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-inner">
          <span className="mark" aria-hidden="true">฿</span>

          {current ? (
            <button
              type="button"
              className="ledger-chip"
              onClick={() => setSwitcherOpen(true)}
              aria-haspopup="dialog"
            >
              <span aria-hidden="true">
                {current.emoji || (current.kind === 'debt' ? '📉' : '📘')}
              </span>
              <span className="ledger-chip-name">{current.name}</span>
              <ShareBadge ledger={current} />
              <span className="ledger-chip-caret" aria-hidden="true">▾</span>
              <span className="sr-only">เปลี่ยนสมุด</span>
            </button>
          ) : (
            <span className="t-heading">Bank</span>
          )}

          <span className="spacer" />
          <span className="t-meta mono" title={`เข้าใช้เป็น ${user?.username}`}>
            {user?.display_name}
          </span>
          <button
            type="button"
            className="btn btn-quiet btn-sm"
            onClick={() => {
              logout()
              navigate('/')
            }}
          >
            ออก
          </button>
        </div>
      </header>

      <div className="shell-body">
        <nav className="rail" aria-label="สมุดและเมนู">
          <div className="rail-section">
            <div className="rail-head">
              <span className="t-label">สมุดของคุณ</span>
              <NavLink to="/ledgers/new" className="btn btn-quiet btn-sm">
                + ใหม่
              </NavLink>
            </div>
          </div>

          <ul className="rail-list">
            {ledgers.map((l) => (
              <li key={l.id}>
                <button
                  type="button"
                  className={`rail-item${l.id === currentId ? ' active' : ''}`}
                  onClick={() => {
                    select(l.id)
                    navigate('/')
                  }}
                  aria-current={l.id === currentId ? 'true' : undefined}
                >
                  <span aria-hidden="true">
                    {l.emoji || (l.kind === 'debt' ? '📉' : '📘')}
                  </span>
                  <span className="rail-item-name">
                    <span className="rail-item-title">{l.name}</span>
                    <ShareBadge ledger={l} />
                  </span>
                  <Money
                    value={l.totals.balance}
                    signed={l.kind !== 'debt'}
                    direction={l.kind === 'debt' ? 'out' : undefined}
                    className="t-meta"
                  />
                </button>
              </li>
            ))}
            {ledgers.length === 0 && (
              <li className="t-meta" style={{ padding: '0 8px' }}>
                ยังไม่มีสมุด
              </li>
            )}
          </ul>

          <div className="rail-nav">
            <NavLink to="/" end className={railLink}>
              รายการ
            </NavLink>
            <NavLink to="/summary" className={railLink}>
              สรุป
            </NavLink>
            <NavLink to="/members" className={railLink}>
              สมาชิก
            </NavLink>
            <NavLink to="/settings" className={railLink}>
              ตั้งค่าสมุด
            </NavLink>
          </div>
        </nav>

        <main className="main">
          <div className="wrap">
            <Outlet />
          </div>
        </main>
      </div>

      <nav className="tabbar" aria-label="เมนูหลัก">
        <NavLink to="/" end className={tab}>
          <span className="tab-glyph" aria-hidden="true">☰</span>
          <span>รายการ</span>
        </NavLink>
        <NavLink to="/new" className={tab}>
          <span className="tab-glyph" aria-hidden="true">＋</span>
          <span>เพิ่ม</span>
        </NavLink>
        <NavLink to="/summary" className={tab}>
          <span className="tab-glyph" aria-hidden="true">▤</span>
          <span>สรุป</span>
        </NavLink>
        <NavLink to="/members" className={tab}>
          <span className="tab-glyph" aria-hidden="true">👥</span>
          <span>สมาชิก</span>
        </NavLink>
      </nav>

      <LedgerSwitcher open={switcherOpen} onClose={() => setSwitcherOpen(false)} />
    </div>
  )
}
