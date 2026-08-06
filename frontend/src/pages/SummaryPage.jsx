import { useEffect, useMemo, useState } from 'react'
import { Navigate } from 'react-router-dom'

import Money from '../components/Money'
import { apiSummary, downloadCsv } from '../api/client'
import { useLedgers } from '../data/LedgerContext'
import { currentMonth, monthOptions } from '../utils/format'

export default function SummaryPage() {
  const { current, currentId, words } = useLedgers()
  const months = useMemo(() => monthOptions(), [])
  const [month, setMonth] = useState(currentMonth)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    if (!currentId) return undefined
    let cancelled = false
    setLoading(true)
    setError(null)
    apiSummary(currentId, month)
      .then((res) => !cancelled && setData(res))
      .catch((err) => !cancelled && setError(err.message || 'โหลดสรุปไม่สำเร็จ'))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [currentId, month])

  if (!current) return <Navigate to="/" replace />

  const exportCsv = async () => {
    setExporting(true)
    try {
      await downloadCsv(currentId, current.name, { month })
    } catch (err) {
      setError(err.message || 'ดาวน์โหลดไม่สำเร็จ')
    } finally {
      setExporting(false)
    }
  }

  const isDebt = current.kind === 'debt'
  const maxCategory = data?.by_category?.reduce(
    (max, row) => Math.max(max, Number(row.total_out), Number(row.total_in)),
    0,
  )

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="t-display" style={{ fontSize: '1.5rem' }}>สรุป</h1>
        <select value={month} onChange={(e) => setMonth(e.target.value)} aria-label="เลือกเดือน">
          {months.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      {error && <p className="notice notice-error">{error}</p>}
      {loading && <p className="t-dim">กำลังโหลด...</p>}

      {data && !loading && (
        <>
          {/* A debt book's headline is what is still owed, all-time. A cashflow
              book's is this month's net. Same payload, different question. */}
          <header className="masthead">
            <span className="t-label">{isDebt ? words.balance : words.periodBalance}</span>
            <div className="masthead-figure">
              {isDebt ? (
                <Money value={data.lifetime.balance} signed={false} direction="out" />
              ) : (
                <Money value={data.period.balance} />
              )}
            </div>
            <div className="masthead-split">
              <div className="stat">
                <span className="t-label">{words.in} เดือนนี้</span>
                <span className="stat-figure">
                  <Money value={data.period.total_in} direction="in" />
                </span>
              </div>
              <div className="stat">
                <span className="t-label">{words.out} เดือนนี้</span>
                <span className="stat-figure">
                  <Money value={data.period.total_out} direction="out" />
                </span>
              </div>
              <div className="stat">
                <span className="t-label">รายการเดือนนี้</span>
                <span className="stat-figure num">{data.period.count}</span>
              </div>
            </div>
          </header>

          {isDebt && (
            <section className="section">
              <div className="section-head">
                <h2 className="t-heading">ตลอดอายุสมุด</h2>
              </div>
              <div className="masthead-split" style={{ padding: 0 }}>
                <div className="stat">
                  <span className="t-label">{words.in} ทั้งหมด</span>
                  <span className="stat-figure">
                    <Money value={data.lifetime.total_in} direction="in" />
                  </span>
                </div>
                <div className="stat">
                  <span className="t-label">{words.out} ทั้งหมด</span>
                  <span className="stat-figure">
                    <Money value={data.lifetime.total_out} direction="out" />
                  </span>
                </div>
                <div className="stat">
                  <span className="t-label">รายการทั้งหมด</span>
                  <span className="stat-figure num">{data.lifetime.count}</span>
                </div>
              </div>
            </section>
          )}

          <section className="section">
            <div className="section-head">
              <h2 className="t-heading">แยกตามคน</h2>
              <span className="t-label">เดือนนี้</span>
            </div>
            {data.by_user.length === 0 ? (
              <p className="t-dim">ยังไม่มีข้อมูล</p>
            ) : (
              <ul className="rows">
                {data.by_user.map((row) => (
                  <li key={row.user.id}>
                    <span className="grow">
                      {row.user.display_name}{' '}
                      <span className="mono t-faint">@{row.user.username}</span>
                    </span>
                    <span className="t-meta num">{row.count} รายการ</span>
                    <Money value={row.total_in} direction="in" />
                    <Money value={row.total_out} direction="out" />
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="section">
            <div className="section-head">
              <h2 className="t-heading">แยกตามหมวดหมู่</h2>
              <span className="t-label">เดือนนี้</span>
            </div>
            {data.by_category.length === 0 ? (
              <p className="t-dim">ยังไม่มีข้อมูล</p>
            ) : (
              <div>
                {data.by_category.map((row) => {
                  const out = Number(row.total_out)
                  const inn = Number(row.total_in)
                  const dominant = out >= inn ? 'out' : 'in'
                  const value = dominant === 'out' ? out : inn
                  const pct = maxCategory ? (value / maxCategory) * 100 : 0
                  return (
                    <div className="bar-row" key={row.category?.id ?? 'none'}>
                      <div className="bar-line">
                        <span>
                          {row.category?.emoji || '·'} {row.category?.name || 'ไม่ระบุหมวด'}
                        </span>
                        <Money value={value} direction={dominant} />
                      </div>
                      <div className="bar-track">
                        <div
                          className={`bar-fill${dominant === 'in' ? ' in' : ''}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </section>

          <section className="section">
            <div className="section-head">
              <h2 className="t-heading">สำรองข้อมูล</h2>
            </div>
            <p className="t-meta" style={{ margin: 0 }}>
              ดาวน์โหลดเก็บไว้เป็นระยะ เผื่อ Neon หรือ Render มีปัญหา
            </p>
            <div className="row">
              <button type="button" className="btn" onClick={exportCsv} disabled={exporting}>
                {exporting ? 'กำลังเตรียมไฟล์...' : `ดาวน์โหลด CSV (${data.period.count} รายการ)`}
              </button>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
