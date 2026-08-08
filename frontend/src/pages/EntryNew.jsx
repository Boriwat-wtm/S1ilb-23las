import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'

import EntryForm from '../components/EntryForm'
import { apiCreateEntry } from '../api/client'
import { useLedgers } from '../data/LedgerContext'

export default function EntryNew() {
  const { current, currentId, canEdit, reload, words } = useLedgers()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  if (!current) return <Navigate to="/" replace />

  if (!canEdit) {
    return (
      <div className="page">
        <div className="notice notice-warn">
          <strong>คุณดูสมุดนี้ได้อย่างเดียว</strong>
          <p>เจ้าของให้สิทธิ์แบบดูเท่านั้น ถ้าต้องการลงรายการให้ขอเปลี่ยนเป็น editor</p>
          <Link className="btn btn-sm" to="/">กลับหน้ารายการ</Link>
        </div>
      </div>
    )
  }

  const submit = async (payload) => {
    setBusy(true)
    setError(null)
    try {
      await apiCreateEntry(currentId, payload)
      // The rail and masthead show balances, so they go stale on every write.
      await reload()
      navigate('/', { replace: true })
    } catch (err) {
      if (err.status === 409) {
        const dupId = err.detail?.duplicate_of_id
        setError(
          dupId ? `สลิปใบนี้ถูกลงในสมุดนี้แล้ว (รายการที่ #${dupId})` : 'สลิปใบนี้ถูกลงไว้แล้ว',
        )
      } else {
        setError(err.message || 'บันทึกไม่สำเร็จ')
      }
      setBusy(false)
    }
  }

  return (
    <div className="page page-narrow">
      {/* Title and destination stack, rather than sitting at opposite ends of
          a 1120px bar with nothing between them. */}
      <header>
        <h1 className="page-title">เพิ่ม{words.entry}</h1>
        <p className="small-print">
          ลงใน {current.emoji} {current.name}
        </p>
      </header>
      <EntryForm mode="create" onSubmit={submit} busy={busy} error={error} />
    </div>
  )
}
