import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { apiCreateLedger } from '../api/client'
import { useLedgers } from '../data/LedgerContext'

const EMOJI = ['📘', '🏠', '🔒', '🚙', '💳', '🍜', '✈️', '🐱', '🎓', '📉']

export default function LedgerNew() {
  const { reload, select } = useLedgers()
  const navigate = useNavigate()

  const [name, setName] = useState('')
  const [kind, setKind] = useState('cashflow')
  const [emoji, setEmoji] = useState('📘')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    if (!name.trim()) return setError('ตั้งชื่อสมุดก่อน')
    setBusy(true)
    setError(null)
    try {
      const ledger = await apiCreateLedger({
        name: name.trim(),
        kind,
        emoji,
        note: note.trim() || null,
      })
      await reload()
      select(ledger.id)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err.message || 'สร้างสมุดไม่สำเร็จ')
      setBusy(false)
    }
    return undefined
  }

  return (
    <div className="page page-narrow">
      <div className="page-head">
        <h1 className="page-title">สร้างสมุดใหม่</h1>
      </div>

      <form className="panel" onSubmit={submit}>
        <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="t-label" style={{ padding: 0, marginBottom: 6 }}>
            ประเภทสมุด
          </legend>
          <div className="segmented" role="group">
            <button
              type="button"
              aria-pressed={kind === 'cashflow'}
              onClick={() => setKind('cashflow')}
            >
              รายรับ–รายจ่าย
            </button>
            <button type="button" aria-pressed={kind === 'debt'} onClick={() => setKind('debt')}>
              ยอดหนี้
            </button>
          </div>
          <p className="t-meta" style={{ margin: '6px 0 0' }}>
            {kind === 'debt'
              ? 'บันทึกหนี้ที่เพิ่มขึ้นและเงินที่จ่ายคืน แล้วดูยอดคงค้าง'
              : 'บันทึกเงินเข้าและเงินออก แล้วดูยอดคงเหลือรายเดือน'}
          </p>
        </fieldset>

        <label className="field">
          <span>ชื่อสมุด</span>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={kind === 'debt' ? 'เช่น หนี้รถ' : 'เช่น บ้านเรา'}
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

        <div className="notice notice-info">
          <p>สมุดนี้จะเป็นส่วนตัวจนกว่าคุณจะเชิญคนอื่นเข้ามาเอง</p>
        </div>

        {error && (
          <p className="notice notice-error" role="alert">
            {error}
          </p>
        )}

        <div className="row">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? 'กำลังสร้าง...' : 'สร้างสมุด'}
          </button>
          <button type="button" className="btn btn-quiet" onClick={() => navigate(-1)}>
            ยกเลิก
          </button>
        </div>
      </form>
    </div>
  )
}
