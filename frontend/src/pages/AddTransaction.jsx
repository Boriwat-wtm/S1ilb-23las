import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import TransactionForm from '../components/TransactionForm'
import { apiCreateTransaction } from '../api/client'

export default function AddTransaction() {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (payload) => {
    setBusy(true)
    setError(null)
    try {
      await apiCreateTransaction(payload)
      navigate('/', { replace: true })
    } catch (err) {
      if (err.status === 409) {
        const dupId = err.detail?.duplicate_of_id
        setError(
          dupId
            ? `สลิปใบนี้ถูกลงไว้แล้ว (รายการที่ #${dupId})`
            : 'สลิปใบนี้ถูกลงไว้แล้ว',
        )
      } else {
        setError(err.message || 'บันทึกไม่สำเร็จ')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <h1 className="page-title">เพิ่มรายการ</h1>
      <TransactionForm mode="add" onSubmit={submit} busy={busy} error={error} />
    </div>
  )
}
