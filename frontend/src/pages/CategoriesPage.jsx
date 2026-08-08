import { useCallback, useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'

import Icon from '../components/Icon'
import {
  apiAddKeyword,
  apiCategoriesDetail,
  apiCreateCategory,
  apiDeleteCategory,
  apiDeleteKeyword,
  apiUpdateCategory,
} from '../api/client'
import { useLedgers } from '../data/LedgerContext'

const SOURCE_LABEL = {
  seed: 'ตั้งต้น',
  learned: 'เรียนจากคุณ',
  ai: 'AI เดา',
  manual: 'คุณเพิ่มเอง',
}

/**
 * The screen that makes automatic keyword writing safe to ship.
 *
 * Two things add rows to this table without asking: the learner, whenever a
 * suggestion is overridden, and the tagger, whenever it is switched on. Both
 * are useful and both can be wrong, and because matching is substring-based a
 * bad word does not announce itself — the symptom is entries quietly landing
 * in the wrong category with nothing to point at. So every word is listed,
 * tagged with who added it, and removable.
 */
export default function CategoriesPage() {
  const { current, currentId, canEdit } = useLedgers()

  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [newCategory, setNewCategory] = useState('')
  const [drafts, setDrafts] = useState({})
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    if (!currentId) return
    setLoading(true)
    try {
      setCategories(await apiCategoriesDetail(currentId))
    } catch (err) {
      setError(err.message || 'โหลดหมวดหมู่ไม่สำเร็จ')
    } finally {
      setLoading(false)
    }
  }, [currentId])

  useEffect(() => {
    load()
  }, [load])

  if (!current) return <Navigate to="/" replace />

  const run = async (fn, onDone) => {
    setError(null)
    setBusy(true)
    try {
      await fn()
      await load()
      onDone?.()
    } catch (err) {
      setError(err.message || 'ทำรายการไม่สำเร็จ')
    } finally {
      setBusy(false)
    }
  }

  const addKeyword = (categoryId) => {
    const word = (drafts[categoryId] || '').trim()
    if (!word) return
    run(
      () => apiAddKeyword(currentId, categoryId, word),
      () => setDrafts((d) => ({ ...d, [categoryId]: '' })),
    )
  }

  const rename = (category) => {
    const next = window.prompt('ชื่อหมวดหมู่ใหม่', category.name)
    if (!next || next.trim() === category.name) return
    run(() => apiUpdateCategory(currentId, category.id, { name: next.trim() }))
  }

  const removeCategory = (category) => {
    const msg =
      category.entry_count > 0
        ? `"${category.name}" มี ${category.entry_count} รายการใช้อยู่ — จะซ่อนจากรายการเลือก แต่รายการเก่ายังคงชื่อหมวดไว้ ทำต่อไหม?`
        : `ลบหมวด "${category.name}" ใช่ไหม?`
    if (!window.confirm(msg)) return
    run(() => apiDeleteCategory(currentId, category.id))
  }

  const learnedCount = categories.reduce(
    (n, c) => n + c.keywords.filter((k) => k.source !== 'seed').length,
    0,
  )

  return (
    <div className="page page-narrow">
      <header className="page-head">
        <div>
          <h1 className="page-title">หมวดหมู่และคำค้น</h1>
          <p className="small-print">
            {current.emoji} {current.name} · {categories.length} หมวด
            {learnedCount > 0 && ` · เรียนรู้เพิ่มมาแล้ว ${learnedCount} คำ`}
          </p>
        </div>
      </header>

      <div className="notice notice-info">
        <p>
          ระบบเดาหมวดจากคำที่อยู่ในชื่อรายการ ทุกครั้งที่คุณแก้หมวดที่มันเดาผิด
          มันจะจำคำนั้นไว้เอง — หน้านี้คือที่ที่คุณดูว่ามันจำอะไรไปบ้าง และลบคำที่ไม่เข้าท่าออก
        </p>
      </div>

      {error && (
        <p className="notice notice-error" role="alert">
          {error}
        </p>
      )}

      {loading ? (
        <p className="t-dim">กำลังโหลด...</p>
      ) : (
        categories.map((c) => (
          <section className="section" key={c.id}>
            <div className="section-head">
              <h2 className="t-heading">
                {c.emoji} {c.name}
              </h2>
              <span className="row">
                <span className="t-label">{c.entry_count} รายการ</span>
                {canEdit && (
                  <>
                    <button
                      type="button"
                      className="btn btn-quiet btn-sm"
                      onClick={() => rename(c)}
                      disabled={busy}
                    >
                      เปลี่ยนชื่อ
                    </button>
                    <button
                      type="button"
                      className="btn btn-quiet btn-icon"
                      onClick={() => removeCategory(c)}
                      disabled={busy}
                      title={`ลบหมวด ${c.name}`}
                    >
                      <Icon name="trash" size={16} />
                      <span className="sr-only">ลบหมวด {c.name}</span>
                    </button>
                  </>
                )}
              </span>
            </div>

            {c.keywords.length === 0 ? (
              <p className="small-print">ยังไม่มีคำค้น — หมวดนี้จะไม่ถูกเดาให้อัตโนมัติ</p>
            ) : (
              <ul className="kw-list">
                {c.keywords.map((k) => (
                  <li key={k.id} className={`kw kw-${k.source}`}>
                    <span className="kw-word">{k.keyword}</span>
                    <span className="kw-source">{SOURCE_LABEL[k.source] || k.source}</span>
                    {canEdit && (
                      <button
                        type="button"
                        className="kw-remove"
                        onClick={() =>
                          run(() => apiDeleteKeyword(currentId, c.id, k.id))
                        }
                        disabled={busy}
                        title={`ลบคำ ${k.keyword}`}
                      >
                        <Icon name="close" size={13} />
                        <span className="sr-only">ลบคำ {k.keyword}</span>
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}

            {canEdit && (
              <div className="toolbar">
                <div className="grow">
                  <input
                    type="text"
                    value={drafts[c.id] || ''}
                    placeholder="เพิ่มคำค้น เช่น after you"
                    aria-label={`เพิ่มคำค้นให้หมวด ${c.name}`}
                    onChange={(e) =>
                      setDrafts((d) => ({ ...d, [c.id]: e.target.value }))
                    }
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        addKeyword(c.id)
                      }
                    }}
                  />
                </div>
                <button
                  type="button"
                  className="btn btn-sm"
                  onClick={() => addKeyword(c.id)}
                  disabled={busy || !(drafts[c.id] || '').trim()}
                >
                  <Icon name="plus" size={15} />
                  เพิ่ม
                </button>
              </div>
            )}
          </section>
        ))
      )}

      {canEdit && (
        <section className="section">
          <div className="section-head">
            <h2 className="t-heading">เพิ่มหมวดใหม่</h2>
          </div>
          <div className="toolbar">
            <div className="grow">
              <input
                type="text"
                value={newCategory}
                placeholder="ชื่อหมวดหมู่"
                aria-label="ชื่อหมวดหมู่ใหม่"
                onChange={(e) => setNewCategory(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && newCategory.trim()) {
                    e.preventDefault()
                    run(
                      () => apiCreateCategory(currentId, { name: newCategory.trim() }),
                      () => setNewCategory(''),
                    )
                  }
                }}
              />
            </div>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={busy || !newCategory.trim()}
              onClick={() =>
                run(
                  () => apiCreateCategory(currentId, { name: newCategory.trim() }),
                  () => setNewCategory(''),
                )
              }
            >
              <Icon name="plus" size={15} />
              สร้าง
            </button>
          </div>
        </section>
      )}

      <p className="small-print">
        คำค้นถูกกรองก่อนบันทึกเสมอ — คำสั้นเกิน 3 ตัว คำกว้างอย่าง “ร้าน” “ค่า” ตัวเลขล้วน
        และคำที่ทับกับหมวดอื่น จะถูกปฏิเสธ เพราะการจับคู่เป็นแบบ substring
        คำกว้างคำเดียวจะกลืนทั้งสมุดโดยไม่มีอะไรฟ้อง
      </p>
    </div>
  )
}
