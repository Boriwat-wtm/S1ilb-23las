import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import TransactionForm from '../components/TransactionForm'
import { apiDeleteTransaction, apiTransaction, apiUpdateTransaction } from '../api/client'

export default function EditTransaction() {
  const { id } = useParams()
  const navigate = useNavigate()

  const [tx, setTx] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [conflict, setConflict] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setTx(await apiTransaction(id))
    } catch (err) {
      setError(err.message || 'โหลดรายการไม่สำเร็จ')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  const submit = async (payload) => {
    setBusy(true)
    setError(null)
    setConflict(null)
    try {
      await apiUpdateTransaction(id, payload)
      navigate('/', { replace: true })
    } catch (err) {
      if (err.status === 409) {
        // The other person saved first. Never overwrite silently — say so and
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
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!window.confirm('ลบรายการนี้ถาวรใช่ไหม?')) return
    setBusy(true)
    try {
      await apiDeleteTransaction(id)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err.message || 'ลบไม่สำเร็จ')
      setBusy(false)
    }
  }

  if (loading) return <div className="page"><p className="muted">กำลังโหลด...</p></div>
  if (!tx) {
    return (
      <div className="page">
        <p className="error-box">{error || 'ไม่พบรายการนี้'}</p>
        <button type="button" className="btn" onClick={() => navigate('/')}>
          กลับหน้ารายการ
        </button>
      </div>
    )
  }

  return (
    <div className="page">
      <h1 className="page-title">แก้ไขรายการ</h1>
      <p className="muted-sm">
        ลงโดย {tx.added_by.display_name} · แก้ล่าสุด v{tx.version}
      </p>
      <TransactionForm
        // Remount on version change so the form re-seeds after a conflict reload.
        key={`${tx.id}-${tx.version}`}
        mode="edit"
        initial={tx}
        onSubmit={submit}
        onDelete={remove}
        busy={busy}
        error={error}
        conflict={conflict}
      />
    </div>
  )
}
