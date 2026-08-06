import { Link } from 'react-router-dom'

import { ShareBadge } from '../components/LedgerSwitcher'
import { useAuth } from '../auth/AuthContext'
import { useLedgers } from '../data/LedgerContext'

/**
 * The mobile counterpart to the desktop rail.
 *
 * Below 900px the rail is hidden and the tab bar has four slots, which is not
 * enough for entries, add, summary, members, ledger settings and account. This
 * page is the fourth slot: everything the rail holds, in a list. Without it,
 * ledger settings were simply unreachable on a phone.
 */
export default function MorePage() {
  const { current, isOwner } = useLedgers()
  const { user, logout } = useAuth()

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="t-display" style={{ fontSize: '1.5rem' }}>เพิ่มเติม</h1>
      </div>

      {current && (
        <section className="section">
          <div className="section-head">
            <h2 className="t-heading">สมุดที่เปิดอยู่</h2>
            <ShareBadge ledger={current} />
          </div>
          <ul className="link-list">
            <li>
              <Link to="/members">
                <span className="link-glyph" aria-hidden="true">👥</span>
                <span className="grow">
                  <span className="link-title">สมาชิก</span>
                  <span className="t-meta">ดูว่าใครเห็นสมุดนี้ และเชิญคนเพิ่ม</span>
                </span>
                <span className="link-caret" aria-hidden="true">›</span>
              </Link>
            </li>
            <li>
              <Link to="/settings">
                <span className="link-glyph" aria-hidden="true">⚙</span>
                <span className="grow">
                  <span className="link-title">ตั้งค่าสมุด</span>
                  <span className="t-meta">
                    {isOwner ? 'ชื่อ ไอคอน เก็บเข้าคลัง ลบสมุด' : 'ดูข้อมูลสมุด (เจ้าของเท่านั้นที่แก้ได้)'}
                  </span>
                </span>
                <span className="link-caret" aria-hidden="true">›</span>
              </Link>
            </li>
          </ul>
        </section>
      )}

      <section className="section">
        <div className="section-head">
          <h2 className="t-heading">สมุด</h2>
        </div>
        <ul className="link-list">
          <li>
            <Link to="/ledgers/new">
              <span className="link-glyph" aria-hidden="true">＋</span>
              <span className="grow">
                <span className="link-title">สร้างสมุดใหม่</span>
                <span className="t-meta">รายรับ–รายจ่าย หรือ ยอดหนี้</span>
              </span>
              <span className="link-caret" aria-hidden="true">›</span>
            </Link>
          </li>
        </ul>
      </section>

      <section className="section">
        <div className="section-head">
          <h2 className="t-heading">บัญชี</h2>
        </div>
        <ul className="link-list">
          <li>
            <Link to="/account">
              <span className="link-glyph" aria-hidden="true">◑</span>
              <span className="grow">
                <span className="link-title">บัญชีของฉัน</span>
                <span className="t-meta">
                  {user?.display_name} · ธีมสี · รหัสผ่าน
                </span>
              </span>
              <span className="link-caret" aria-hidden="true">›</span>
            </Link>
          </li>
          <li>
            <button type="button" onClick={logout}>
              <span className="link-glyph" aria-hidden="true">⏻</span>
              <span className="grow">
                <span className="link-title">ออกจากระบบ</span>
                <span className="t-meta">เฉพาะเครื่องนี้</span>
              </span>
            </button>
          </li>
        </ul>
      </section>
    </div>
  )
}
