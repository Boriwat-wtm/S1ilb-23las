import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { apiTransactions } from '../api/client'
import { useRefData } from '../data/RefDataContext'
import {
  currentMonth,
  fmtDateShort,
  fmtMoney,
  fmtTime,
  groupByDay,
  monthOptions,
} from '../utils/format'

const PAGE_SIZE = 50

/**
 * Filters and offset live in one state object on purpose. Split across two
 * useStates, changing a filter would fire one fetch at the stale offset before
 * the reset landed — a wasted request and a visible append-then-replace flash.
 * Here every filter change resets the offset in the same update.
 */
const initialQuery = () => ({
  month: currentMonth(),
  categoryId: '',
  addedById: '',
  q: '',
  offset: 0,
})

export default function Dashboard() {
  const { categories, users } = useRefData()
  const months = useMemo(() => monthOptions(), [])

  const [query, setQuery] = useState(initialQuery)
  const [searchText, setSearchText] = useState('')

  const [page, setPage] = useState(null)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const setFilter = useCallback((patch) => {
    setQuery((prev) => ({ ...prev, ...patch, offset: 0 }))
  }, [])

  // Debounced search — also folded into the same update, offset included.
  useEffect(() => {
    const t = setTimeout(() => {
      const trimmed = searchText.trim()
      setQuery((prev) => (prev.q === trimmed ? prev : { ...prev, q: trimmed, offset: 0 }))
    }, 350)
    return () => clearTimeout(t)
  }, [searchText])

  // Guards against an out-of-order response overwriting a newer one.
  const requestId = useRef(0)

  useEffect(() => {
    const id = ++requestId.current
    setLoading(true)
    setError(null)

    apiTransactions({
      month: query.month,
      category_id: query.categoryId,
      added_by_id: query.addedById,
      q: query.q,
      limit: PAGE_SIZE,
      offset: query.offset,
    })
      .then((res) => {
        if (id !== requestId.current) return
        setPage(res)
        setItems((prev) => (query.offset === 0 ? res.items : [...prev, ...res.items]))
      })
      .catch((err) => {
        if (id !== requestId.current) return
        setError(err.message || 'โหลดรายการไม่สำเร็จ')
      })
      .finally(() => {
        if (id === requestId.current) setLoading(false)
      })
  }, [query])

  const days = useMemo(() => groupByDay(items), [items])
  const hasMore = page ? items.length < page.total : false
  const filtersActive = Boolean(query.categoryId || query.addedById || query.q)

  return (
    <div className="page">
      <div className="month-row">
        <select
          className="month-select"
          value={query.month}
          onChange={(e) => setFilter({ month: e.target.value })}
          aria-label="เลือกเดือน"
        >
          {months.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
        <div className="month-total">
          <span className="muted-sm">รวม</span>
          <strong>{page ? fmtMoney(page.total_amount) : '—'}</strong>
        </div>
      </div>

      <div className="filters">
        <input
          type="search"
          className="filter-search"
          placeholder="ค้นหารายการ..."
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
        />
        <div className="filter-row">
          <select
            value={query.addedById}
            onChange={(e) => setFilter({ addedById: e.target.value })}
            aria-label="คนลง"
          >
            <option value="">ทุกคน</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.display_name}
              </option>
            ))}
          </select>
          <select
            value={query.categoryId}
            onChange={(e) => setFilter({ categoryId: e.target.value })}
            aria-label="หมวดหมู่"
          >
            <option value="">ทุกหมวด</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.emoji ? `${c.emoji} ` : ''}
                {c.name}
              </option>
            ))}
          </select>
          {filtersActive && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => {
                setSearchText('')
                setFilter({ categoryId: '', addedById: '', q: '' })
              }}
            >
              ล้าง
            </button>
          )}
        </div>
      </div>

      {error && <p className="error-box">{error}</p>}

      {!loading && items.length === 0 && !error && (
        <div className="empty">
          <p>{filtersActive ? 'ไม่มีรายการที่ตรงกับตัวกรอง' : 'ยังไม่มีรายการในเดือนนี้'}</p>
          <Link className="btn btn-primary" to="/add">
            เพิ่มรายการแรก
          </Link>
        </div>
      )}

      {days.map((day) => (
        <section key={day.key} className="day-group">
          <header className="day-head">
            <span>{fmtDateShort(day.date)}</span>
            <span className="muted-sm">{fmtMoney(day.total)}</span>
          </header>
          <ul className="tx-list">
            {day.items.map((tx) => (
              <li key={tx.id}>
                <Link to={`/edit/${tx.id}`} className="tx-item">
                  <span className="tx-emoji" aria-hidden="true">
                    {tx.category?.emoji || '💸'}
                  </span>
                  <span className="tx-main">
                    <span className="tx-desc">{tx.description}</span>
                    <span className="tx-meta">
                      {tx.category?.name || 'ไม่ระบุหมวด'} · {tx.added_by.display_name} ·{' '}
                      {fmtTime(tx.occurred_at)}
                      {tx.slip_path && ' · 📎'}
                    </span>
                  </span>
                  <span className="tx-amount">{fmtMoney(tx.amount)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}

      {loading && <p className="muted center">กำลังโหลด...</p>}

      {hasMore && !loading && (
        <button
          type="button"
          className="btn btn-block"
          onClick={() => setQuery((prev) => ({ ...prev, offset: prev.offset + PAGE_SIZE }))}
        >
          โหลดเพิ่ม ({items.length}/{page.total})
        </button>
      )}
    </div>
  )
}
