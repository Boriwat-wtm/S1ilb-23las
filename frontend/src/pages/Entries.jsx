import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import EntryList from '../components/EntryList'
import EntryTable from '../components/EntryTable'
import Money from '../components/Money'
import { apiEntries } from '../api/client'
import { useLedgers } from '../data/LedgerContext'
import { currentMonth, fmtMoney, monthOptions } from '../utils/format'

const PAGE_SIZE = 50
const VIEW_KEY = 'bank.view'

const initialQuery = () => ({
  month: currentMonth(),
  categoryId: '',
  createdById: '',
  direction: '',
  q: '',
  offset: 0,
})

/**
 * Filters and offset live in one state object. Split across two useStates, a
 * filter change fires one fetch at the stale offset before the reset lands —
 * a wasted request and a visible append-then-replace flash.
 */
export default function Entries() {
  const { current, currentId, categories, words, canEdit, loading: ledgersLoading } = useLedgers()
  const months = useMemo(() => monthOptions(), [])

  const [view, setView] = useState(() => {
    try {
      return localStorage.getItem(VIEW_KEY) || 'list'
    } catch {
      return 'list'
    }
  })
  // Collapsed on phones, always open from 720px. Two rows of controls ahead of
  // the data costs a third of a small screen before a single number is visible.
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [query, setQuery] = useState(initialQuery)
  const [searchText, setSearchText] = useState('')
  const [page, setPage] = useState(null)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const setFilter = useCallback((patch) => {
    setQuery((prev) => ({ ...prev, ...patch, offset: 0 }))
  }, [])

  const chooseView = (next) => {
    setView(next)
    try {
      localStorage.setItem(VIEW_KEY, next)
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    const t = setTimeout(() => {
      const trimmed = searchText.trim()
      setQuery((prev) => (prev.q === trimmed ? prev : { ...prev, q: trimmed, offset: 0 }))
    }, 350)
    return () => clearTimeout(t)
  }, [searchText])

  // Switching books must not carry the previous book's filters or rows.
  useEffect(() => {
    setQuery(initialQuery())
    setSearchText('')
    setItems([])
    setPage(null)
  }, [currentId])

  const requestId = useRef(0)

  useEffect(() => {
    if (!currentId) {
      setLoading(false)
      return
    }
    const id = ++requestId.current
    setLoading(true)
    setError(null)

    apiEntries(currentId, {
      month: query.month,
      category_id: query.categoryId,
      created_by_id: query.createdById,
      direction: query.direction,
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
  }, [currentId, query])

  if (ledgersLoading && !current) {
    return <div className="page"><p className="t-dim">กำลังโหลด...</p></div>
  }

  if (!current) {
    return (
      <div className="page">
        <div className="empty">
          <h1 className="t-heading">ยังไม่มีสมุด</h1>
          <p className="t-dim">
            สร้างสมุดเล่มแรก — จะเป็นส่วนตัวจนกว่าคุณจะเชิญคนอื่นเข้ามา
          </p>
          <Link className="btn btn-primary" to="/ledgers/new">
            สร้างสมุดใหม่
          </Link>
        </div>
      </div>
    )
  }

  const hasMore = page ? items.length < page.total : false
  const activeFilterCount = [query.categoryId, query.createdById, query.direction, query.q].filter(
    Boolean,
  ).length
  const filtersActive = activeFilterCount > 0
  const totals = page?.totals

  return (
    <div className="page">
      {/* The one dominant element: what this book is worth right now. */}
      <header className="masthead">
        <div className="spread" style={{ alignItems: 'baseline' }}>
          <span className="t-label">
            {words.balance}
            {query.month && current.kind !== 'debt' ? ` · ${months.find((m) => m.value === query.month)?.label ?? ''}` : ''}
          </span>
          {current.kind === 'debt' && (
            <span className="t-meta">ทั้งหมด {current.totals.count} รายการ</span>
          )}
        </div>

        <div className="masthead-figure">
          {current.kind === 'debt' ? (
            <Money value={current.totals.balance} signed={false} direction="out" />
          ) : (
            <Money value={totals?.balance ?? 0} />
          )}
        </div>

        {current.kind === 'debt' && Number(current.totals.total_in) > 0 && (
          <>
            <div
              className="progress"
              role="img"
              aria-label={`จ่ายคืนแล้ว ${fmtMoney(current.totals.total_out)} จากทั้งหมด ${fmtMoney(current.totals.total_in)} บาท`}
            >
              <div
                className="progress-fill"
                style={{
                  width: `${Math.min(100, (Number(current.totals.total_out) / Number(current.totals.total_in)) * 100)}%`,
                }}
              />
            </div>
            <span className="t-meta">
              จ่ายคืนแล้ว {fmtMoney(current.totals.total_out)} จาก {fmtMoney(current.totals.total_in)} บาท
            </span>
          </>
        )}

        <div className="masthead-split">
          <div className="stat">
            <span className="t-label">{words.in}</span>
            <span className="stat-figure">
              <Money value={totals?.total_in ?? 0} direction="in" />
            </span>
          </div>
          <div className="stat">
            <span className="t-label">{words.out}</span>
            <span className="stat-figure">
              <Money value={totals?.total_out ?? 0} direction="out" />
            </span>
          </div>
          <div className="stat">
            <span className="t-label">จำนวนรายการ</span>
            <span className="stat-figure num">{page?.total ?? 0}</span>
          </div>
        </div>
      </header>

      <div className="toolbar">
        <select
          className="month-pick"
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

        <div className="segmented" role="group" aria-label="รูปแบบการแสดงผล">
          <button type="button" aria-pressed={view === 'list'} onClick={() => chooseView('list')}>
            รายการ
          </button>
          <button type="button" aria-pressed={view === 'table'} onClick={() => chooseView('table')}>
            ตาราง
          </button>
        </div>

        <button
          type="button"
          className="btn btn-sm filter-toggle"
          onClick={() => setFiltersOpen((o) => !o)}
          aria-expanded={filtersOpen}
          aria-controls="entry-filters"
        >
          ตัวกรอง{activeFilterCount > 0 ? ` (${activeFilterCount})` : ''}
        </button>

        <span className="spacer" />

        {canEdit && (
          <Link className="btn btn-primary btn-sm" to="/new">
            + เพิ่มรายการ
          </Link>
        )}
      </div>

      <div
        id="entry-filters"
        className={`toolbar filter-bar${filtersOpen ? ' open' : ''}`}
      >
        <div className="grow">
          <input
            type="search"
            placeholder="ค้นหารายการ..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            aria-label="ค้นหารายการ"
          />
        </div>
        <select
          value={query.direction}
          onChange={(e) => setFilter({ direction: e.target.value })}
          aria-label="ประเภท"
        >
          <option value="">ทั้งเข้าและออก</option>
          <option value="in">{words.in}</option>
          <option value="out">{words.out}</option>
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
            className="btn btn-quiet btn-sm"
            onClick={() => {
              setSearchText('')
              setFilter({ categoryId: '', createdById: '', direction: '', q: '' })
            }}
          >
            ล้างตัวกรอง
          </button>
        )}
      </div>

      {error && (
        <p className="notice notice-error" role="alert">
          {error}
        </p>
      )}

      {!loading && items.length === 0 && !error && (
        <div className="empty">
          <p>{filtersActive ? 'ไม่มีรายการที่ตรงกับตัวกรอง' : 'ยังไม่มีรายการในเดือนนี้'}</p>
          {canEdit && !filtersActive && (
            <Link className="btn btn-primary" to="/new">
              เพิ่มรายการแรก
            </Link>
          )}
        </div>
      )}

      {items.length > 0 &&
        (view === 'table' ? (
          <EntryTable entries={items} filterBalance={totals?.balance ?? 0} words={words} />
        ) : (
          <EntryList entries={items} />
        ))}

      {loading && <p className="t-dim" style={{ textAlign: 'center' }}>กำลังโหลด...</p>}

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
