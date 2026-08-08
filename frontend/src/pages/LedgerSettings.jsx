import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'

import Money from '../components/Money'
import { apiDeleteLedger, apiUpdateLedger } from '../api/client'
import { useLedgers } from '../data/LedgerContext'
import { fmtDateShort } from '../utils/format'

const EMOJI = ['📘', '🏠', '🔒', '🚙', '💳', '🍜', '✈️', '🐱', '🎓', '📉']

export default function LedgerSettings() {
  const { current, currentId, isOwner, reload, select, words } = useLedgers()
  const navigate = useNavigate()

  const [name, setName] = useState('')
  const [emoji, setEmoji] = useState('📘')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (!current) return
    setName(current.name)
    setEmoji(current.emoji || '📘')
    setNote(current.note || '')
  }, [current])

  if (!current) return <Navigate to="/" replace />

  const save = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setSaved(false)
    try {
      await apiUpdateLedger(currentId, { name: name.trim(), emoji, note: note.trim() || null })
      await reload()
      setSaved(true)
    } catch (err) {
      setError(err.message || 'บันทึกไม่สำเร็จ')
    } finally {
      setBusy(false)
    }
  }

  const archive = async () => {
    setBusy(true)
    try {
      await apiUpdateLedger(currentId, { archived: !current.archived })
      await reload()
      select(null)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err.message || 'ทำไม่สำเร็จ')
      setBusy(false)
    }
  }

  const destroy = async () => {
    const typed = window.prompt(
      `ลบสมุด "${current.name}" พร้อมทุกรายการในนั้นถาวร กู้คืนไม่ได้\n\nพิมพ์ชื่อสมุดเพื่อยืนยัน:`,
    )
    if (typed !== current.name) {
      if (typed !== null) setError('ชื่อไม่ตรง ยกเลิกการลบแล้ว')
      return
    }
    setBusy(true)
    try {
      await apiDeleteLedger(currentId)
      select(null)
      await reload()
      navigate('/', { replace: true })
    } catch (err) {
      setError(err.message || 'ลบไม่สำเร็จ')
      setBusy(false)
    }
  }

  return (
    <div className="page page-narrow">
      <div className="page-head">
        <h1 className="page-title">ตั้งค่าสมุด</h1>
        <span className="t-meta">
          สร้างเมื่อ {fmtDateShort(current.created_at)} · เจ้าของ {current.owner.display_name}
        </span>
      </div>

      <section className="section">
        <div className="section-head">
          <h2 className="t-heading">ยอดรวม</h2>
          <span className="t-label">ตลอดอายุสมุด</span>
        </div>
        <div className="masthead-split" style={{ padding: 0 }}>
          <div className="stat">
            <span className="t-label">{words.balance}</span>
            <span className="stat-figure">
              <Money
                value={current.totals.balance}
                signed={current.kind !== 'debt'}
                direction={current.kind === 'debt' ? 'out' : undefined}
              />
            </span>
          </div>
          <div className="stat">
            <span className="t-label">{words.in}</span>
            <span className="stat-figure">
              <Money value={current.totals.total_in} direction="in" />
            </span>
          </div>
          <div className="stat">
            <span className="t-label">{words.out}</span>
            <span className="stat-figure">
              <Money value={current.totals.total_out} direction="out" />
            </span>
          </div>
          <div className="stat">
            <span className="t-label">รายการ</span>
            <span className="stat-figure num">{current.totals.count}</span>
          </div>
        </div>
      </section>

      {!isOwner ? (
        <div className="notice notice-info">
          <p>
            เฉพาะเจ้าของสมุด ({current.owner.display_name}) เท่านั้นที่แก้ตั้งค่าได้
          </p>
        </div>
      ) : (
        <>
          <form className="panel" onSubmit={save}>
            <label className="field">
              <span>ชื่อสมุด</span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={80}
                required
              />
            </label>

            <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
              <legend className="t-label" style={{ padding: 0, marginBottom: 6 }}>
                ไอคอน
              </legend>
              <div className="row">
                {EMOJI.map((e) => (
                  <button
                    key={e}
                    type="button"
                    className="btn btn-sm"
                    aria-pressed={emoji === e}
                    onClick={() => setEmoji(e)}
                    style={
                      emoji === e
                        ? { borderColor: 'var(--accent)', background: 'var(--accent-soft)' }
                        : undefined
                    }
                  >
                    {e}
                  </button>
                ))}
              </div>
            </fieldset>

            <label className="field">
              <span>คำอธิบาย</span>
              <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} />
            </label>

            <p className="t-meta" style={{ margin: 0 }}>
              ประเภทสมุด ({current.kind === 'debt' ? 'ยอดหนี้' : 'รายรับ–รายจ่าย'})
              เปลี่ยนทีหลังไม่ได้ เพราะหมวดหมู่กับความหมายของเงินเข้า-ออกผูกกับมัน
            </p>

            {error && (
              <p className="notice notice-error" role="alert">
                {error}
              </p>
            )}
            {saved && <p className="t-meta">บันทึกแล้ว</p>}

            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? 'กำลังบันทึก...' : 'บันทึก'}
            </button>
          </form>

          <section className="section">
            <div className="section-head">
              <h2 className="t-heading">เขตอันตราย</h2>
            </div>
            <div className="panel">
              <div className="spread">
                <div>
                  <strong>{current.archived ? 'เอากลับมาใช้' : 'เก็บเข้าคลัง'}</strong>
                  <p className="t-meta" style={{ margin: 0 }}>
                    ซ่อนจากรายการสมุด แต่ข้อมูลยังอยู่ครบ
                  </p>
                </div>
                <button type="button" className="btn" onClick={archive} disabled={busy}>
                  {current.archived ? 'เอากลับมา' : 'เก็บเข้าคลัง'}
                </button>
              </div>

              <div className="spread" style={{ borderTop: '1px solid var(--rule)', paddingTop: 12 }}>
                <div>
                  <strong>ลบสมุดถาวร</strong>
                  <p className="t-meta" style={{ margin: 0 }}>
                    ลบ {current.totals.count} รายการและสมาชิกทั้งหมด กู้คืนไม่ได้
                  </p>
                </div>
                <button type="button" className="btn btn-danger" onClick={destroy} disabled={busy}>
                  ลบสมุด
                </button>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
