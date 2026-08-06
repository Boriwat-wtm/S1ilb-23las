import { useEffect, useMemo, useState } from 'react'

import { apiSummary, downloadCsv } from '../api/client'
import { currentMonth, fmtMoney, monthOptions } from '../utils/format'

export default function Summary() {
  const months = useMemo(() => monthOptions(), [])
  const [month, setMonth] = useState(currentMonth)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    apiSummary(month)
      .then((res) => {
        if (!cancelled) setData(res)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'โหลดสรุปไม่สำเร็จ')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [month])

  const exportCsv = async () => {
    setExporting(true)
    try {
      await downloadCsv({ month })
    } catch (err) {
      setError(err.message || 'ดาวน์โหลดไม่สำเร็จ')
    } finally {
      setExporting(false)
    }
  }

  const maxCategory = data?.by_category?.reduce(
    (max, row) => Math.max(max, Number(row.total)),
    0,
  )

  return (
    <div className="page">
      <div className="month-row">
        <select
          className="month-select"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
          aria-label="เลือกเดือน"
        >
          {months.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      {error && <p className="error-box">{error}</p>}
      {loading && <p className="muted center">กำลังโหลด...</p>}

      {data && !loading && (
        <>
          <section className="card total-card">
            <span className="muted-sm">รายจ่ายรวมเดือนนี้</span>
            <strong className="total-big">฿{fmtMoney(data.total)}</strong>
            <span className="muted-sm">{data.count} รายการ</span>
          </section>

          <section className="card">
            <div className="card-head">
              <h2>แยกตามคน</h2>
            </div>
            {data.by_user.length === 0 && <p className="muted">ยังไม่มีข้อมูล</p>}
            <ul className="split-list">
              {data.by_user.map((row) => (
                <li key={row.user.id}>
                  <span>{row.user.display_name}</span>
                  <span className="muted-sm">{row.count} รายการ</span>
                  <strong>{fmtMoney(row.total)}</strong>
                </li>
              ))}
            </ul>
          </section>

          <section className="card">
            <div className="card-head">
              <h2>แยกตามหมวดหมู่</h2>
            </div>
            {data.by_category.length === 0 && <p className="muted">ยังไม่มีข้อมูล</p>}
            <ul className="cat-list">
              {data.by_category.map((row) => {
                const pct = maxCategory ? (Number(row.total) / maxCategory) * 100 : 0
                return (
                  <li key={row.category?.id ?? 'none'}>
                    <div className="cat-line">
                      <span className="cat-name">
                        {row.category?.emoji || '💸'} {row.category?.name || 'ไม่ระบุหมวด'}
                      </span>
                      <strong>{fmtMoney(row.total)}</strong>
                    </div>
                    <div className="cat-bar">
                      <div className="cat-bar-fill" style={{ width: `${pct}%` }} />
                    </div>
                  </li>
                )
              })}
            </ul>
          </section>

          <section className="card">
            <div className="card-head">
              <h2>สำรองข้อมูล</h2>
            </div>
            <p className="hint">
              ดาวน์โหลดเก็บไว้เป็นระยะ เผื่อ Neon หรือ Render มีปัญหา
            </p>
            <button
              type="button"
              className="btn btn-block"
              onClick={exportCsv}
              disabled={exporting}
            >
              {exporting ? 'กำลังเตรียมไฟล์...' : 'ดาวน์โหลด CSV เดือนนี้'}
            </button>
          </section>
        </>
      )}
    </div>
  )
}
