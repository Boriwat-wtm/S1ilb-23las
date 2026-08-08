import { useCallback, useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'

import {
  apiInvite,
  apiMembers,
  apiRemoveMember,
  apiSetMemberRole,
} from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { useLedgers } from '../data/LedgerContext'
import { fmtDateShort } from '../utils/format'

const ROLE_LABEL = {
  owner: 'เจ้าของ',
  editor: 'ลงรายการได้',
  viewer: 'ดูอย่างเดียว',
}

export default function MembersPage() {
  const { current, currentId, isOwner, reload } = useLedgers()
  const { user } = useAuth()
  const navigate = useNavigate()

  const [members, setMembers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [username, setUsername] = useState('')
  const [role, setRole] = useState('viewer')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    if (!currentId) return
    setLoading(true)
    try {
      setMembers(await apiMembers(currentId))
    } catch (err) {
      setError(err.message || 'โหลดรายชื่อสมาชิกไม่สำเร็จ')
    } finally {
      setLoading(false)
    }
  }, [currentId])

  useEffect(() => {
    load()
  }, [load])

  if (!current) return <Navigate to="/" replace />

  const invite = async (e) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await apiInvite(currentId, username.trim().toLowerCase(), role)
      setUsername('')
      await load()
      await reload()
    } catch (err) {
      setError(err.message || 'เชิญไม่สำเร็จ')
    } finally {
      setBusy(false)
    }
  }

  const changeRole = async (memberId, nextRole) => {
    setError(null)
    try {
      await apiSetMemberRole(currentId, memberId, nextRole)
      await load()
    } catch (err) {
      setError(err.message || 'เปลี่ยนสิทธิ์ไม่สำเร็จ')
    }
  }

  const remove = async (member) => {
    const isSelf = member.user.id === user?.id
    const msg = isSelf
      ? `ออกจากสมุด "${current.name}" ใช่ไหม? คุณจะไม่เห็นข้อมูลในสมุดนี้อีก`
      : `เอา ${member.user.display_name} ออกจากสมุดนี้ใช่ไหม?`
    if (!window.confirm(msg)) return

    setError(null)
    try {
      await apiRemoveMember(currentId, member.id)
      await reload()
      if (isSelf) navigate('/', { replace: true })
      else await load()
    } catch (err) {
      setError(err.message || 'เอาออกไม่สำเร็จ')
    }
  }

  return (
    <div className="page page-narrow">
      <div className="page-head">
        <h1 className="page-title">สมาชิก</h1>
        <span className="t-meta">
          {current.emoji} {current.name}
        </span>
      </div>

      {/* Who can read this book is stated plainly, because that is the entire
          reason the app exists. */}
      <div className={`notice ${members.length > 1 ? 'notice-info' : ''}`}>
        <p>
          {members.length > 1
            ? `สมุดนี้แชร์อยู่กับอีก ${members.length - 1} คน — ทุกคนในรายชื่อข้างล่างเห็นทุกรายการในสมุดนี้`
            : 'สมุดนี้เป็นส่วนตัว มีแค่คุณที่เห็น'}
        </p>
      </div>

      {error && (
        <p className="notice notice-error" role="alert">
          {error}
        </p>
      )}

      <section className="section">
        <div className="section-head">
          <h2 className="t-heading">คนที่เข้าถึงได้</h2>
          <span className="t-label">{members.length} คน</span>
        </div>

        {loading ? (
          <p className="t-dim">กำลังโหลด...</p>
        ) : (
          <ul className="rows">
            {members.map((m) => {
              const isSelf = m.user.id === user?.id
              return (
                <li key={m.id}>
                  <span className="grow">
                    <span style={{ display: 'block', fontWeight: 550 }}>
                      {m.user.display_name}
                      {isSelf && <span className="t-faint"> (คุณ)</span>}
                    </span>
                    <span className="mono t-faint">@{m.user.username}</span>
                    <span className="t-faint"> · เข้าร่วม {fmtDateShort(m.created_at)}</span>
                  </span>

                  {m.role === 'owner' || !isOwner ? (
                    <span className={`role-tag ${m.role}`}>{ROLE_LABEL[m.role]}</span>
                  ) : (
                    <select
                      value={m.role}
                      onChange={(e) => changeRole(m.id, e.target.value)}
                      aria-label={`สิทธิ์ของ ${m.user.display_name}`}
                      style={{ width: 'auto', fontSize: '0.85rem', padding: '5px 8px' }}
                    >
                      <option value="viewer">{ROLE_LABEL.viewer}</option>
                      <option value="editor">{ROLE_LABEL.editor}</option>
                    </select>
                  )}

                  {m.role !== 'owner' && (isOwner || isSelf) && (
                    <button
                      type="button"
                      className="btn btn-danger btn-sm"
                      onClick={() => remove(m)}
                    >
                      {isSelf ? 'ออกจากสมุด' : 'เอาออก'}
                    </button>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </section>

      {isOwner && (
        <section className="section">
          <div className="section-head">
            <h2 className="t-heading">เชิญคนเข้ามา</h2>
          </div>
          <form className="panel" onSubmit={invite}>
            <label className="field">
              <span>ชื่อผู้ใช้ของเขา</span>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="เช่น fon"
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck="false"
                required
              />
              <span className="field-hint">
                เขาต้องสมัครไว้ก่อน แล้วบอกชื่อผู้ใช้ให้คุณ
              </span>
            </label>

            <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
              <legend className="t-label" style={{ padding: 0, marginBottom: 6 }}>
                ให้สิทธิ์แค่ไหน
              </legend>
              <div className="segmented" role="group">
                <button
                  type="button"
                  aria-pressed={role === 'viewer'}
                  onClick={() => setRole('viewer')}
                >
                  ดูอย่างเดียว
                </button>
                <button
                  type="button"
                  aria-pressed={role === 'editor'}
                  onClick={() => setRole('editor')}
                >
                  ลงรายการได้
                </button>
              </div>
              <p className="t-meta" style={{ margin: '6px 0 0' }}>
                {role === 'viewer'
                  ? 'เห็นทุกรายการ แต่เพิ่ม/แก้/ลบไม่ได้'
                  : 'เห็นทุกรายการ และเพิ่ม แก้ ลบรายการได้ แต่จัดการสมาชิกไม่ได้'}
              </p>
            </fieldset>

            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? 'กำลังเชิญ...' : 'เชิญเข้าสมุด'}
            </button>
          </form>
        </section>
      )}
    </div>
  )
}
