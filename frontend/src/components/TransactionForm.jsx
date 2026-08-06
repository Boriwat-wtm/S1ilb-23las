import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { apiSlipUrl, apiSuggestCategory, apiUploadSlip } from '../api/client'
import { useRefData } from '../data/RefDataContext'
import { nowLocalInputValue, toLocalInputValue } from '../utils/format'

const AMOUNT_RE = /^-?\d{0,9}(\.\d{0,2})?$/

/**
 * The form is the source of truth, always. Slip upload and category guessing
 * only ever prefill it — every field stays editable, and nothing here blocks
 * on either of them succeeding.
 */
export default function TransactionForm({
  mode = 'add',
  initial = null,
  onSubmit,
  onDelete,
  busy = false,
  error = null,
  conflict = null,
}) {
  const { categories } = useRefData()

  const [occurredAt, setOccurredAt] = useState(
    initial ? toLocalInputValue(initial.occurred_at) : nowLocalInputValue(),
  )
  const [description, setDescription] = useState(initial?.description ?? '')
  const [amount, setAmount] = useState(initial ? String(initial.amount) : '')
  const [categoryId, setCategoryId] = useState(
    initial?.category?.id ? String(initial.category.id) : '',
  )
  const [note, setNote] = useState(initial?.note ?? '')
  const [formError, setFormError] = useState(null)

  // Once the user picks a category themselves, stop second-guessing them.
  const [categoryTouched, setCategoryTouched] = useState(Boolean(initial?.category))
  const [suggestedBy, setSuggestedBy] = useState(null)

  const [slip, setSlip] = useState({
    path: initial?.slip_path ?? null,
    url: null,
    ref: null,
    source: initial?.source ?? 'manual',
    rawText: null,
    confidence: null,
  })
  const [uploading, setUploading] = useState(false)
  const [slipMessage, setSlipMessage] = useState(null)
  const [duplicateId, setDuplicateId] = useState(null)
  const fileInputRef = useRef(null)
  const objectUrlRef = useRef(null)

  // --- existing slip: fetch a fresh signed URL to preview -----------------
  useEffect(() => {
    if (mode !== 'edit' || !initial?.slip_path || !initial?.id) return
    let cancelled = false
    apiSlipUrl(initial.id)
      .then((r) => {
        if (!cancelled) setSlip((s) => ({ ...s, url: r.signed_url }))
      })
      .catch(() => {
        if (!cancelled) setSlipMessage('โหลดรูปสลิปไม่ได้ (ข้อมูลรายการยังแก้ได้ตามปกติ)')
      })
    return () => {
      cancelled = true
    }
  }, [mode, initial?.id, initial?.slip_path])

  useEffect(
    () => () => {
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current)
    },
    [],
  )

  // --- category auto-suggest ----------------------------------------------
  useEffect(() => {
    if (categoryTouched) return
    const text = description.trim()
    if (!text) {
      setSuggestedBy(null)
      return undefined
    }
    const controller = new AbortController()
    const timer = setTimeout(async () => {
      try {
        const res = await apiSuggestCategory(text, controller.signal)
        if (res?.category) {
          setCategoryId(String(res.category.id))
          setSuggestedBy(res.matched_keyword)
        } else {
          setSuggestedBy(null)
        }
      } catch {
        /* a failed guess is not worth telling anyone about */
      }
    }, 400)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [description, categoryTouched])

  // --- slip upload ---------------------------------------------------------
  const handleFile = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return

    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current)
    objectUrlRef.current = URL.createObjectURL(file)
    setSlip((s) => ({ ...s, url: objectUrlRef.current }))
    setUploading(true)
    setSlipMessage(null)
    setDuplicateId(null)

    try {
      const res = await apiUploadSlip(file)
      setSlip({
        path: res.slip_path,
        url: res.signed_url || objectUrlRef.current,
        ref: res.slip_ref,
        source: res.source || 'manual',
        rawText: res.raw_text,
        confidence: res.confidence,
      })
      if (res.amount != null) setAmount(String(res.amount))
      if (res.occurred_at) setOccurredAt(toLocalInputValue(res.occurred_at))
      if (res.description) setDescription(res.description)
      if (res.suggestion?.category && !categoryTouched) {
        setCategoryId(String(res.suggestion.category.id))
        setSuggestedBy(res.suggestion.matched_keyword)
      }
      if (res.duplicate_of_id) setDuplicateId(res.duplicate_of_id)
      setSlipMessage(res.message)
    } catch (err) {
      // Upload failure must not trap the user — the form is still fully usable.
      setSlip((s) => ({ ...s, path: null, url: null }))
      setSlipMessage(`${err.message} — กรอกรายการเองได้ตามปกติ`)
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const clearSlip = () => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current)
      objectUrlRef.current = null
    }
    setSlip({ path: null, url: null, ref: null, source: 'manual', rawText: null, confidence: null })
    setSlipMessage(null)
    setDuplicateId(null)
  }

  const onAmountChange = (e) => {
    const v = e.target.value.replace(/[^\d.\-]/g, '')
    if (v === '' || AMOUNT_RE.test(v)) setAmount(v)
  }

  // --- submit --------------------------------------------------------------
  const submit = (e) => {
    e.preventDefault()
    setFormError(null)

    if (!description.trim()) return setFormError('กรอกชื่อรายการด้วย')
    if (!amount || Number.isNaN(Number(amount))) return setFormError('กรอกจำนวนเงินให้ถูกต้อง')
    if (Number(amount) === 0) return setFormError('จำนวนเงินต้องไม่เป็น 0')
    if (!occurredAt) return setFormError('เลือกวันที่และเวลาด้วย')

    const payload = {
      occurred_at: occurredAt, // naive — the backend reads this as Bangkok time
      description: description.trim(),
      amount,
      category_id: categoryId ? Number(categoryId) : null,
      note: note.trim() || null,
      slip_path: slip.path,
    }

    if (mode === 'add') {
      payload.slip_ref = slip.ref
      payload.source = slip.source
      payload.ocr_raw_text = slip.rawText
      payload.ocr_confidence = slip.confidence
    } else {
      payload.version = initial.version
    }

    return onSubmit(payload)
  }

  const shownError = formError || error

  return (
    <form className="tx-form" onSubmit={submit}>
      {conflict && (
        <div className="banner banner-warn" role="alert">
          <strong>อีกฝ่ายเพิ่งแก้รายการนี้</strong>
          <p>{conflict.message}</p>
          <button type="button" className="btn btn-sm" onClick={conflict.onReload}>
            โหลดข้อมูลล่าสุด
          </button>
        </div>
      )}

      {/* --- slip ---------------------------------------------------------- */}
      <section className="card">
        <div className="card-head">
          <h2>สลิป</h2>
          <span className="muted-sm">ไม่บังคับ</span>
        </div>

        {slip.url ? (
          <div className="slip-preview">
            <img src={slip.url} alt="สลิปที่แนบไว้" />
            {uploading && <div className="slip-uploading">กำลังอัปโหลด...</div>}
            <button type="button" className="btn btn-ghost btn-sm" onClick={clearSlip}>
              เอาสลิปออก
            </button>
          </div>
        ) : (
          <label className="slip-drop">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              onChange={handleFile}
              hidden
            />
            <span className="slip-drop-icon" aria-hidden="true">📸</span>
            <span>{uploading ? 'กำลังอัปโหลด...' : 'ถ่ายรูป / เลือกสลิป'}</span>
          </label>
        )}

        {slipMessage && <p className="hint">{slipMessage}</p>}

        {duplicateId && (
          <div className="banner banner-warn">
            <strong>สลิปใบนี้เคยลงไว้แล้ว</strong>
            <Link className="btn btn-sm" to={`/edit/${duplicateId}`}>
              ดูรายการเดิม
            </Link>
          </div>
        )}
      </section>

      {/* --- fields -------------------------------------------------------- */}
      <section className="card">
        <label className="field">
          <span>รายการ</span>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="เช่น กาแฟเซเว่น"
            maxLength={255}
            required
          />
        </label>

        <label className="field">
          <span>จำนวนเงิน (บาท)</span>
          <input
            type="text"
            inputMode="decimal"
            value={amount}
            onChange={onAmountChange}
            placeholder="0.00"
            className="input-amount"
            required
          />
        </label>

        <label className="field">
          <span>วันที่และเวลา</span>
          <input
            type="datetime-local"
            value={occurredAt}
            onChange={(e) => setOccurredAt(e.target.value)}
            required
          />
        </label>

        <label className="field">
          <span>
            หมวดหมู่
            {suggestedBy && !categoryTouched && (
              <em className="suggest-tag">เดาจาก “{suggestedBy}”</em>
            )}
          </span>
          <select
            value={categoryId}
            onChange={(e) => {
              setCategoryId(e.target.value)
              setCategoryTouched(true)
              setSuggestedBy(null)
            }}
          >
            <option value="">— ไม่ระบุ —</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.emoji ? `${c.emoji} ` : ''}
                {c.name}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>หมายเหตุ</span>
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} />
        </label>
      </section>

      {shownError && <p className="error-box" role="alert">{shownError}</p>}

      <div className="form-actions">
        <button type="submit" className="btn btn-primary btn-block" disabled={busy || uploading}>
          {busy ? 'กำลังบันทึก...' : mode === 'add' ? 'บันทึก' : 'บันทึกการแก้ไข'}
        </button>
        {onDelete && (
          <button type="button" className="btn btn-danger btn-block" onClick={onDelete} disabled={busy}>
            ลบรายการนี้
          </button>
        )}
      </div>
    </form>
  )
}
