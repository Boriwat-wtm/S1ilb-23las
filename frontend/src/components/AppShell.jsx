import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'

import Icon from './Icon'
import LedgerSwitcher, { ShareBadge, ledgerGlyph } from './LedgerSwitcher'
import Money from './Money'
import ThemePicker from './ThemePicker'
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
  const [themeOpen, setThemeOpen] = useState(false)
  const navigate = useNavigate()

  const tab = ({ isActive }) => `tab${isActive ? ' active' : ''}`
  const railLink = ({ isActive }) => `rail-nav-item${isActive ? ' active' : ''}`

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
              {ledgerGlyph(current)}
              <span className="ledger-chip-name">{current.name}</span>
              <ShareBadge ledger={current} />
              <Icon name="chevronDown" size={15} className="ledger-chip-caret" />
              <span className="sr-only">เปลี่ยนสมุด</span>
            </button>
          ) : (
            <span className="t-heading">Bank</span>
          )}

          <span className="spacer" />
          <span className="t-meta mono topbar-user" title={`เข้าใช้เป็น ${user?.username}`}>
            {user?.display_name}
          </span>
          {/* Reachable from every screen on both layouts — a theme you have to
              go hunting for in a settings page is a theme nobody changes. */}
          <button
            type="button"
            className="btn btn-quiet btn-icon"
            onClick={() => setThemeOpen(true)}
            aria-haspopup="dialog"
            title="เปลี่ยนธีมสี"
          >
            <Icon name="contrast" size={18} />
            <span className="sr-only">เปลี่ยนธีมสี</span>
          </button>
          <button
            type="button"
            className="btn btn-quiet btn-icon"
            onClick={() => {
              logout()
              navigate('/')
            }}
            title="ออกจากระบบ"
          >
            <Icon name="logout" size={18} />
            <span className="sr-only">ออกจากระบบ</span>
          </button>
        </div>
      </header>

      <div className="shell-body">
        <nav className="rail" aria-label="สมุดและเมนู">
          <div className="rail-section">
            <div className="rail-head">
              <span className="t-label">สมุดของคุณ</span>
              <NavLink to="/ledgers/new" className="btn btn-quiet btn-sm">
                <Icon name="plus" size={15} />
                ใหม่
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
                  {ledgerGlyph(l)}
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
              <Icon name="list" size={18} />
              รายการ
            </NavLink>
            <NavLink to="/summary" className={railLink}>
              <Icon name="chart" size={18} />
              สรุป
            </NavLink>
            <NavLink to="/members" className={railLink}>
              <Icon name="users" size={18} />
              สมาชิก
            </NavLink>
            <NavLink to="/categories" className={railLink}>
              <Icon name="list" size={18} />
              หมวดหมู่
            </NavLink>
            <NavLink to="/settings" className={railLink}>
              <Icon name="gear" size={18} />
              ตั้งค่าสมุด
            </NavLink>
            <NavLink to="/account" className={railLink}>
              <Icon name="user" size={18} />
              บัญชีของฉัน
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
          <Icon name="list" size={21} />
          <span>รายการ</span>
        </NavLink>
        <NavLink to="/new" className={tab}>
          <Icon name="plus" size={21} />
          <span>เพิ่ม</span>
        </NavLink>
        <NavLink to="/summary" className={tab}>
          <Icon name="chart" size={21} />
          <span>สรุป</span>
        </NavLink>
        {/* Four slots cannot hold members, ledger settings and account, so the
            last one opens the list that does. Before this, ledger settings had
            no route to it at all on a phone. */}
        <NavLink to="/more" className={tab}>
          <Icon name="more" size={21} />
          <span>เพิ่มเติม</span>
        </NavLink>
      </nav>

      <LedgerSwitcher open={switcherOpen} onClose={() => setSwitcherOpen(false)} />
      <ThemePicker open={themeOpen} onClose={() => setThemeOpen(false)} />
    </div>
  )
}
