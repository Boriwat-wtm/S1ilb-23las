import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import EntryForm from '../components/EntryForm'
import { apiDeleteEntry, apiEntry, apiUpdateEntry } from '../api/client'
import { useLedgers } from '../data/LedgerContext'
import { fmtDateTime } from '../utils/format'

export default function EntryEdit() {
  const { id } = useParams()
  const { currentId, canEdit, reload } = useLedgers()
  const navigate = useNavigate()

  const [entry, setEntry] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [conflict, setConflict] = useState(null)

  const load = useCallback(async () => {
    if (!currentId) return
    setLoading(true)
    setError(null)
    try {
      setEntry(await apiEntry(currentId, id))
    } catch (err) {
      setError(err.message || 'โหลดรายการไม่สำเร็จ')
    } finally {
      setLoading(false)
    }
  }, [currentId, id])

  useEffect(() => {
    load()
  }, [load])

  const submit = async (payload) => {
    setBusy(true)
    setError(null)
    setConflict(null)
    try {
      await apiUpdateEntry(currentId, id, payload)
      await reload()
      navigate('/', { replace: true })
    } catch (err) {
      if (err.status === 409) {
        // Someone else saved first. Never overwrite silently — say so, and
        // offer to pull their version in.
        setConflict({
          message:
            err.detail?.message ||
            'ข้อมูลถูกแก้ไปแล้วหลังจากคุณเปิดหน้านี้ โหลดใหม่แล้วแก้อีกครั้ง',
          onReload: () => {
            setConflict(null)
            load()
          },
        })
      } else {
        setError(err.message || 'บันทึกไม่สำเร็จ')
      }
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!window.confirm('ลบรายการนี้ถาวรใช่ไหม?')) return
    setBusy(true)
    try {
      await apiDeleteEntry(currentId, id)
      await reload()
      navigate('/', { replace: true })
    } catch (err) {
      setError(err.message || 'ลบไม่สำเร็จ')
      setBusy(false)
    }
  }

  if (loading) return <div className="page page-narrow"><p className="t-dim">กำลังโหลด...</p></div>

  if (!entry) {
    return (
      <div className="page page-narrow">
        <p className="notice notice-error">{error || 'ไม่พบรายการนี้'}</p>
        <Link className="btn" to="/">กลับหน้ารายการ</Link>
      </div>
    )
  }

  return (
    <div className="page page-narrow">
      <div className="page-head">
        <h1 className="page-title">
          {canEdit ? 'แก้ไขรายการ' : 'รายละเอียดรายการ'}
        </h1>
        <span className="t-meta">
          ลงโดย {entry.created_by.display_name} · {fmtDateTime(entry.created_at)}
          {entry.version > 1 && ` · แก้แล้ว ${entry.version - 1} ครั้ง`}
        </span>
      </div>

      {!canEdit && (
        <div className="notice notice-info">
          <p>คุณดูสมุดนี้ได้อย่างเดียว จึงแก้รายการไม่ได้</p>
        </div>
      )}

      <EntryForm
        // Remount on version change so the form re-seeds after a conflict reload.
        key={`${entry.id}-${entry.version}`}
        mode="edit"
        initial={entry}
        onSubmit={canEdit ? submit : () => {}}
        onDelete={canEdit ? remove : undefined}
        busy={busy || !canEdit}
        error={error}
        conflict={conflict}
      />
    </div>
  )
}
