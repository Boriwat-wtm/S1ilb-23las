import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import Icon from '../components/Icon'
import { ledgerGlyph } from '../components/LedgerSwitcher'
import Money from '../components/Money'
import { ThemeOptions } from '../components/ThemePicker'
import { useAuth } from '../auth/AuthContext'
import { useLedgers } from '../data/LedgerContext'

export default function AccountPage() {
  const { user, logout, updateProfile, changePassword } = useAuth()
  const { ledgers } = useLedgers()
  const navigate = useNavigate()

  const [displayName, setDisplayName] = useState(user?.display_name ?? '')
  const [profileBusy, setProfileBusy] = useState(false)
  const [profileMsg, setProfileMsg] = useState(null)
  const [profileError, setProfileError] = useState(null)

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [pwBusy, setPwBusy] = useState(false)
  const [pwMsg, setPwMsg] = useState(null)
  const [pwError, setPwError] = useState(null)

  useEffect(() => {
    setDisplayName(user?.display_name ?? '')
  }, [user?.display_name])

  const saveProfile = async (e) => {
    e.preventDefault()
    setProfileError(null)
    setProfileMsg(null)
    if (!displayName.trim()) return setProfileError('ต้องกรอกชื่อที่แสดง')
    setProfileBusy(true)
    try {
      await updateProfile(displayName)
      setProfileMsg('บันทึกแล้ว')
    } catch (err) {
      setProfileError(err.message || 'บันทึกไม่สำเร็จ')
    } finally {
      setProfileBusy(false)
    }
    return undefined
  }

  const savePassword = async (e) => {
    e.preventDefault()
    setPwError(null)
    setPwMsg(null)
    if (newPassword.length < 8) return setPwError('รหัสผ่านใหม่ต้องยาวอย่างน้อย 8 ตัว')
    if (newPassword !== confirmPassword) return setPwError('รหัสผ่านใหม่ทั้งสองช่องไม่ตรงกัน')
    setPwBusy(true)
    try {
      await changePassword(currentPassword, newPassword)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setPwMsg('เปลี่ยนรหัสผ่านแล้ว — อุปกรณ์อื่นที่ค้างอยู่ถูกให้ออกจากระบบทั้งหมด')
    } catch (err) {
      setPwError(err.message || 'เปลี่ยนรหัสผ่านไม่สำเร็จ')
    } finally {
      setPwBusy(false)
    }
    return undefined
  }

  const owned = ledgers.filter((l) => l.my_role === 'owner')
  const guest = ledgers.filter((l) => l.my_role !== 'owner')

  return (
    <div className="page page-narrow">
      <div className="page-head">
        <h1 className="page-title">บัญชีของฉัน</h1>
      </div>

      {/* --- identity ------------------------------------------------------ */}
      <section className="section">
        <div className="section-head">
          <h2 className="t-heading">โปรไฟล์</h2>
        </div>

        <form className="panel" onSubmit={saveProfile}>
          <div className="field">
            <span>ชื่อผู้ใช้</span>
            <div className="static-field mono">@{user?.username}</div>
            <span className="field-hint">
              เปลี่ยนไม่ได้ — คนอื่นใช้ชื่อนี้เชิญคุณเข้าสมุด ถ้าเปลี่ยนได้ คำเชิญที่ส่งไปแล้วจะพัง
            </span>
          </div>

          <label className="field">
            <span>ชื่อที่แสดง</span>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              maxLength={80}
              required
            />
            <span className="field-hint">
              ชื่อนี้จะขึ้นข้างรายการที่คุณลงในทุกสมุด
            </span>
          </label>

          {profileError && (
            <p className="notice notice-error" role="alert">{profileError}</p>
          )}
          {profileMsg && <p className="t-meta">{profileMsg}</p>}

          <button
            type="submit"
            className="btn btn-primary"
            disabled={profileBusy || displayName.trim() === user?.display_name}
          >
            {profileBusy ? 'กำลังบันทึก...' : 'บันทึกโปรไฟล์'}
          </button>
        </form>
      </section>

      {/* --- theme ---------------------------------------------------------- */}
      <section className="section">
        <div className="section-head">
          <h2 className="t-heading">ธีมสี</h2>
          <span className="t-label">เก็บไว้ในเครื่องนี้</span>
        </div>
        <ThemeOptions />
      </section>

      {/* --- password ------------------------------------------------------- */}
      <section className="section">
        <div className="section-head">
          <h2 className="t-heading">รหัสผ่าน</h2>
        </div>
        <form className="panel" onSubmit={savePassword}>
          <label className="field">
            <span>รหัสผ่านปัจจุบัน</span>
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <div className="grid-2">
            <label className="field">
              <span>รหัสผ่านใหม่</span>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
                required
              />
            </label>
            <label className="field">
              <span>ยืนยันรหัสผ่านใหม่</span>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                required
              />
            </label>
          </div>

          <p className="small-print">
            อย่างน้อย 8 ตัว · เปลี่ยนแล้วอุปกรณ์อื่นที่ยังค้างอยู่จะถูกให้ออกจากระบบทั้งหมด
          </p>

          {pwError && <p className="notice notice-error" role="alert">{pwError}</p>}
          {pwMsg && <p className="notice notice-info">{pwMsg}</p>}

          <button type="submit" className="btn btn-primary" disabled={pwBusy}>
            {pwBusy ? 'กำลังเปลี่ยน...' : 'เปลี่ยนรหัสผ่าน'}
          </button>
        </form>
      </section>

      {/* --- ledgers overview ----------------------------------------------- */}
      <section className="section">
        <div className="section-head">
          <h2 className="t-heading">สมุดทั้งหมด</h2>
          <span className="t-label">{ledgers.length} เล่ม</span>
        </div>
        <ul className="rows">
          {owned.map((l) => (
            <li key={l.id}>
              {ledgerGlyph(l)}
              <span className="grow">
                <span className="rail-item-title">{l.name}</span>
                <span className="field-hint">
                  {l.kind === 'debt' ? 'ยอดหนี้' : 'รายรับ–รายจ่าย'} ·{' '}
                  {l.member_count > 1 ? `แชร์กับ ${l.member_count - 1} คน` : 'ส่วนตัว'}
                </span>
              </span>
              <span className="role-tag owner">เจ้าของ</span>
              <Money
                value={l.totals.balance}
                signed={l.kind !== 'debt'}
                direction={l.kind === 'debt' ? 'out' : undefined}
              />
            </li>
          ))}
          {guest.map((l) => (
            <li key={l.id}>
              {ledgerGlyph(l)}
              <span className="grow">
                <span className="rail-item-title">{l.name}</span>
                <span className="field-hint">
                  ของ {l.owner.display_name}
                </span>
              </span>
              <span className="role-tag">
                {l.my_role === 'editor' ? 'ลงรายการได้' : 'ดูอย่างเดียว'}
              </span>
              <Money
                value={l.totals.balance}
                signed={l.kind !== 'debt'}
                direction={l.kind === 'debt' ? 'out' : undefined}
              />
            </li>
          ))}
          {ledgers.length === 0 && <li className="t-dim">ยังไม่มีสมุด</li>}
        </ul>
      </section>

      {/* --- account -------------------------------------------------------- */}
      <section className="section">
        <div className="section-head">
          <h2 className="t-heading">บัญชี</h2>
        </div>
        <div className="panel">
          <div className="spread">
            <div>
              <strong>ออกจากระบบ</strong>
              <p className="t-meta" style={{ margin: 0 }}>เฉพาะเครื่องนี้</p>
            </div>
            <button
              type="button"
              className="btn"
              onClick={() => {
                logout()
                navigate('/')
              }}
            >
              ออกจากระบบ
            </button>
          </div>

          {/* Stated rather than quietly absent: an entry carries who wrote it,
              and in a shared book that attribution belongs to the other
              members as much as to you. Deleting the author would either erase
              their records or leave rows with no name on them, so the honest
              path is the manual one that already exists. */}
          <div className="notice" style={{ borderLeftColor: 'var(--rule-strong)' }}>
            <strong>ยังไม่มีปุ่มลบบัญชี</strong>
            <p>
              รายการที่คุณลงในสมุดของคนอื่นมีชื่อคุณกำกับอยู่ ถ้าลบบัญชีทิ้ง
              รายการเหล่านั้นจะหายไปจากสมุดของเขา หรือไม่ก็เหลือแถวที่ไม่มีชื่อคนลง
              ซึ่งทั้งสองอย่างไม่ควรเกิดโดยที่เจ้าของสมุดไม่รู้
            </p>
            <p>
              ถ้าต้องการเลิกใช้: ออกจากสมุดของคนอื่นในหน้าสมาชิก แล้วลบสมุดของตัวเองในหน้าตั้งค่าสมุด
            </p>
          </div>
        </div>
      </section>

    </div>
  )
}
