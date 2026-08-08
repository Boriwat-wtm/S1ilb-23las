import { Link } from 'react-router-dom'

import Icon from '../components/Icon'
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
function Row({ to, onClick, icon, title, hint }) {
  const body = (
    <>
      <span className="link-glyph">
        <Icon name={icon} size={19} />
      </span>
      <span className="grow">
        <span className="link-title">{title}</span>
        <span className="t-meta">{hint}</span>
      </span>
      {to && <Icon name="chevronRight" size={17} className="link-caret" />}
    </>
  )
  return (
    <li>
      {to ? (
        <Link to={to}>{body}</Link>
      ) : (
        <button type="button" onClick={onClick}>
          {body}
        </button>
      )}
    </li>
  )
}

export default function MorePage() {
  const { current, isOwner } = useLedgers()
  const { user, logout } = useAuth()

  return (
    <div className="page page-narrow">
      <div className="page-head">
        <h1 className="page-title">เพิ่มเติม</h1>
      </div>

      {current && (
        <section className="section">
          <div className="section-head">
            <h2 className="t-heading">สมุดที่เปิดอยู่</h2>
            <ShareBadge ledger={current} />
          </div>
          <ul className="link-list">
            <Row
              to="/members"
              icon="users"
              title="สมาชิก"
              hint="ดูว่าใครเห็นสมุดนี้ และเชิญคนเพิ่ม"
            />
            <Row
              to="/settings"
              icon="gear"
              title="ตั้งค่าสมุด"
              hint={
                isOwner
                  ? 'ชื่อ ไอคอน เก็บเข้าคลัง ลบสมุด'
                  : 'ดูข้อมูลสมุด (เจ้าของเท่านั้นที่แก้ได้)'
              }
            />
          </ul>
        </section>
      )}

      <section className="section">
        <div className="section-head">
          <h2 className="t-heading">สมุด</h2>
        </div>
        <ul className="link-list">
          <Row
            to="/ledgers/new"
            icon="plus"
            title="สร้างสมุดใหม่"
            hint="รายรับ–รายจ่าย หรือ ยอดหนี้"
          />
        </ul>
      </section>

      <section className="section">
        <div className="section-head">
          <h2 className="t-heading">บัญชี</h2>
        </div>
        <ul className="link-list">
          <Row
            to="/account"
            icon="user"
            title="บัญชีของฉัน"
            hint={`${user?.display_name} · ธีมสี · รหัสผ่าน`}
          />
          <Row onClick={logout} icon="logout" title="ออกจากระบบ" hint="เฉพาะเครื่องนี้" />
        </ul>
      </section>
    </div>
  )
}
