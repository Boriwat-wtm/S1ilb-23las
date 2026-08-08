import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'

import Icon from '../components/Icon'
import Money from '../components/Money'
import { apiCreateEntriesBatch, apiUploadSlip } from '../api/client'
import { useLedgers } from '../data/LedgerContext'
import { entryEffect, nowLocalInputValue, toLocalInputValue } from '../utils/format'

const MAX_ROWS = 50
// Render's free tier is 0.1 vCPU and every upload costs it a decode, a resize
// and a re-encode. Two at a time keeps a ten-slip drop from timing out the
// whole queue, and still finishes far faster than one at a time.
const UPLOAD_CONCURRENCY = 2

let seq = 0
const nextId = () => {
  seq += 1
  return `d${seq}`
}

const blankDraft = (overrides = {}) => ({
  id: nextId(),
  status: 'ready',
  message: null,
  file: null,
  previewUrl: null,
  slipPath: null,
  slipRef: null,
  source: 'manual',
  rawText: null,
  confidence: null,
  direction: 'out',
  amount: '',
  description: '',
  occurredAt: nowLocalInputValue(),
  categoryId: '',
  error: null,
  ...overrides,
})

/**
 * Add many entries in one pass.
 *
 * The single-entry form is fine for one purchase, but a week of unfiled slips
 * through it is: tap add, fill, save, wait, tap add again — five round trips
 * per slip. Here the whole stack goes in at once, each slip becomes a draft
 * row, and one button saves what survived review.
 *
 * Rows are drafts, not entries: nothing reaches the ledger until "บันทึกทั้งหมด",
 * so a misread slip is corrected in place rather than saved and then edited.
 */
export default function BatchEntry() {
  const { current, currentId, categories, canEdit, words, reload } = useLedgers()
  const navigate = useNavigate()

  const [drafts, setDrafts] = useState([])
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [savedCount, setSavedCount] = useState(0)
  const fileRef = useRef(null)
  const objectUrls = useRef(new Set())

  useEffect(
    () => () => {
      objectUrls.current.forEach((u) => URL.revokeObjectURL(u))
    },
    [],
  )

  const patch = useCallback((id, changes) => {
    setDrafts((rows) => rows.map((r) => (r.id === id ? { ...r, ...changes } : r)))
  }, [])

  // --- slip intake ---------------------------------------------------------
  const runQueue = useCallback(
    async (queued) => {
      let cursor = 0
      const worker = async () => {
        while (cursor < queued.length) {
          const item = queued[cursor]
          cursor += 1
          patch(item.id, { status: 'uploading' })
          try {
            const res = await apiUploadSlip(currentId, item.file)
            patch(item.id, {
              status: 'ready',
              slipPath: res.slip_path,
              slipRef: res.slip_ref,
              source: res.source || 'manual',
              rawText: res.raw_text,
              confidence: res.confidence,
              message: res.duplicate_of_id
                ? `สลิปใบนี้เคยลงไว้แล้ว (รายการ #${res.duplicate_of_id})`
                : res.message,
              ...(res.amount != null ? { amount: String(res.amount) } : {}),
              ...(res.occurred_at ? { occurredAt: toLocalInputValue(res.occurred_at) } : {}),
              ...(res.description ? { description: res.description } : {}),
              ...(res.suggestion?.category
                ? { categoryId: String(res.suggestion.category.id) }
                : {}),
            })
          } catch (err) {
            // A slip that fails to upload still leaves a usable row — the
            // amount is on the paper in the user's hand either way.
            patch(item.id, {
              status: 'failed',
              message: `${err.message} — กรอกแถวนี้เองได้`,
            })
          }
        }
      }
      await Promise.all(
        Array.from({ length: Math.min(UPLOAD_CONCURRENCY, queued.length) }, worker),
      )
    },
    [currentId, patch],
  )

  const addFiles = (event) => {
    const picked = Array.from(event.target.files || [])
    if (fileRef.current) fileRef.current.value = ''
    if (!picked.length) return

    const room = MAX_ROWS - drafts.length
    const files = picked.slice(0, Math.max(0, room))
    if (files.length < picked.length) {
      setSaveError(`เพิ่มได้สูงสุด ${MAX_ROWS} รายการต่อรอบ — ตัดส่วนเกินออกแล้ว`)
    }

    const created = files.map((file) => {
      const previewUrl = URL.createObjectURL(file)
      objectUrls.current.add(previewUrl)
      return blankDraft({ file, previewUrl, status: 'queued', source: 'ocr' })
    })
    setDrafts((rows) => [...rows, ...created])
    runQueue(created)
  }

  const removeDraft = (id) => {
    setDrafts((rows) => {
      const row = rows.find((r) => r.id === id)
      if (row?.previewUrl) {
        URL.revokeObjectURL(row.previewUrl)
        objectUrls.current.delete(row.previewUrl)
      }
      return rows.filter((r) => r.id !== id)
    })
  }

  // --- save ----------------------------------------------------------------
  const busy = drafts.some((d) => d.status === 'queued' || d.status === 'uploading')
  const invalid = drafts.filter(
    (d) => !d.description.trim() || !d.amount || Number(d.amount) <= 0,
  )
  const total = drafts.reduce(
    (sum, d) => sum + (Number(d.amount) > 0 ? entryEffect({ ...d, amount: d.amount }) : 0),
    0,
  )

  const saveAll = async () => {
    if (!drafts.length) return
    if (invalid.length) {
      setSaveError(`มี ${invalid.length} แถวที่ยังไม่ได้กรอกรายการหรือจำนวนเงิน`)
      return
    }
    setSaving(true)
    setSaveError(null)

    const payload = drafts.map((d) => ({
      occurred_at: d.occurredAt,
      description: d.description.trim(),
      amount: d.amount,
      direction: d.direction,
      category_id: d.categoryId ? Number(d.categoryId) : null,
      slip_path: d.slipPath,
      slip_ref: d.slipRef,
      source: d.source,
      ocr_raw_text: d.rawText,
      ocr_confidence: d.confidence,
    }))

    try {
      const res = await apiCreateEntriesBatch(currentId, payload)
      await reload()
      setSavedCount(res.created.length)

      if (!res.errors.length) {
        navigate('/', { replace: true })
        return
      }
      // Keep only what failed, carrying the server's reason onto the row.
      const byIndex = new Map(res.errors.map((e) => [e.index, e.message]))
      setDrafts((rows) =>
        rows
          .map((row, i) => (byIndex.has(i) ? { ...row, error: byIndex.get(i) } : null))
          .filter(Boolean),
      )
      setSaveError(
        `บันทึกได้ ${res.created.length} รายการ · เหลือ ${res.errors.length} รายการที่มีปัญหา`,
      )
    } catch (err) {
      setSaveError(err.message || 'บันทึกไม่สำเร็จ')
    } finally {
      setSaving(false)
    }
  }

  if (!current) return <Navigate to="/" replace />

  if (!canEdit) {
    return (
      <div className="page page-narrow">
        <div className="notice notice-warn">
          <strong>คุณดูสมุดนี้ได้อย่างเดียว</strong>
          <Link className="btn btn-sm" to="/">กลับหน้ารายการ</Link>
        </div>
      </div>
    )
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1 className="page-title">เพิ่มหลายรายการ</h1>
          <p className="small-print">
            ลงใน {current.emoji} {current.name} · ยังไม่บันทึกจนกว่าจะกดปุ่มข้างล่าง
          </p>
        </div>
        <Link className="btn btn-quiet btn-sm" to="/new">
          เพิ่มทีละรายการ
        </Link>
      </header>

      <div className="row">
        <label className="btn btn-primary">
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            multiple
            onChange={addFiles}
            hidden
          />
          <Icon name="camera" size={17} />
          เลือกสลิปหลายใบ
        </label>
        <button
          type="button"
          className="btn"
          onClick={() => setDrafts((rows) => [...rows, blankDraft()])}
          disabled={drafts.length >= MAX_ROWS}
        >
          <Icon name="plus" size={16} />
          เพิ่มแถวว่าง
        </button>
      </div>

      {current.kind !== 'debt' && (
        <p className="small-print">
          เลือกได้หลายใบพร้อมกัน แต่ละใบจะกลายเป็นหนึ่งแถวให้ตรวจก่อนบันทึก
        </p>
      )}

      {saveError && (
        <p className="notice notice-warn" role="alert">
          {saveError}
        </p>
      )}
      {savedCount > 0 && drafts.length > 0 && (
        <p className="small-print">บันทึกไปแล้ว {savedCount} รายการในรอบนี้</p>
      )}

      {drafts.length === 0 ? (
        <div className="empty">
          <p>ยังไม่มีแถว — เลือกสลิปหลายใบ หรือเพิ่มแถวว่างเพื่อกรอกเอง</p>
        </div>
      ) : (
        <ul className="draft-list">
          {drafts.map((d, i) => (
            <li key={d.id} className={`draft${d.error ? ' has-error' : ''}`}>
              <div className="draft-index num">{i + 1}</div>

              <div className="draft-body">
                <div className="draft-line">
                  <div className="segmented dir" role="group" aria-label="ประเภท">
                    <button
                      type="button"
                      data-dir="out"
                      aria-pressed={d.direction === 'out'}
                      onClick={() => patch(d.id, { direction: 'out' })}
                    >
                      − {words.out}
                    </button>
                    <button
                      type="button"
                      data-dir="in"
                      aria-pressed={d.direction === 'in'}
                      onClick={() => patch(d.id, { direction: 'in' })}
                    >
                      + {words.in}
                    </button>
                  </div>

                  <span className="amount-box draft-amount">
                    <span className="baht" aria-hidden="true">฿</span>
                    <input
                      type="text"
                      inputMode="decimal"
                      className="input-amount"
                      value={d.amount}
                      placeholder="0.00"
                      aria-label={`จำนวนเงิน แถวที่ ${i + 1}`}
                      onChange={(e) => {
                        const v = e.target.value.replace(/[^\d.]/g, '')
                        if (v === '' || /^\d{0,9}(\.\d{0,2})?$/.test(v)) {
                          patch(d.id, { amount: v })
                        }
                      }}
                    />
                  </span>

                  <button
                    type="button"
                    className="btn btn-quiet btn-icon"
                    onClick={() => removeDraft(d.id)}
                    title="เอาแถวนี้ออก"
                  >
                    <Icon name="trash" size={17} />
                    <span className="sr-only">เอาแถวที่ {i + 1} ออก</span>
                  </button>
                </div>

                <input
                  type="text"
                  value={d.description}
                  placeholder="รายการ เช่น กาแฟเซเว่น"
                  aria-label={`รายการ แถวที่ ${i + 1}`}
                  maxLength={255}
                  onChange={(e) => patch(d.id, { description: e.target.value })}
                />

                <div className="draft-line">
                  <input
                    type="datetime-local"
                    value={d.occurredAt}
                    aria-label={`วันที่ แถวที่ ${i + 1}`}
                    onChange={(e) => patch(d.id, { occurredAt: e.target.value })}
                  />
                  <select
                    value={d.categoryId}
                    aria-label={`หมวดหมู่ แถวที่ ${i + 1}`}
                    onChange={(e) => patch(d.id, { categoryId: e.target.value })}
                  >
                    <option value="">— ไม่ระบุหมวด —</option>
                    {categories.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.emoji ? `${c.emoji} ` : ''}
                        {c.name}
                      </option>
                    ))}
                  </select>
                </div>

                {(d.status === 'queued' || d.status === 'uploading') && (
                  <p className="small-print">
                    {d.status === 'queued' ? 'รอคิวอ่านสลิป...' : 'กำลังอัปโหลดและอ่านสลิป...'}
                  </p>
                )}
                {d.message && <p className="small-print">{d.message}</p>}
                {d.error && (
                  <p className="draft-error" role="alert">
                    {d.error}
                  </p>
                )}
              </div>

              {d.previewUrl && (
                <img className="draft-thumb" src={d.previewUrl} alt={`สลิปแถวที่ ${i + 1}`} />
              )}
            </li>
          ))}
        </ul>
      )}

      {drafts.length > 0 && (
        <div className="draft-footer">
          <div className="spread">
            <span className="t-label">รวม {drafts.length} รายการ</span>
            <Money value={total} />
          </div>
          <button
            type="button"
            className="btn btn-primary btn-block btn-lg"
            onClick={saveAll}
            disabled={saving || busy}
          >
            {saving
              ? 'กำลังบันทึก...'
              : busy
                ? 'รออ่านสลิปให้เสร็จก่อน...'
                : `บันทึกทั้งหมด ${drafts.length} รายการ`}
          </button>
        </div>
      )}
    </div>
  )
}
