import { useEffect, useRef } from 'react'

import { useTheme } from '../theme/ThemeContext'

/**
 * Each option shows the theme's actual four colours — paper, ink, credit,
 * accent — rather than a name and a moon icon. Picking applies immediately
 * with the sheet still open, so the choice is judged against the real
 * interface behind it instead of a swatch.
 */
export default function ThemePicker({ open, onClose }) {
  const { theme, setTheme, themes } = useTheme()
  const panelRef = useRef(null)
  const previousFocus = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    previousFocus.current = document.activeElement
    panelRef.current?.querySelector('button')?.focus()

    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      previousFocus.current?.focus?.()
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="sheet-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="เลือกธีม"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="sheet" ref={panelRef}>
        <div className="section-head">
          <h2 className="t-heading">ธีมสี</h2>
          <button type="button" className="btn btn-quiet btn-sm" onClick={onClose}>
            ปิด
          </button>
        </div>

        <ul className="theme-list">
          {themes.map((t) => (
            <li key={t.id}>
              <button
                type="button"
                className={`theme-option${theme === t.id ? ' active' : ''}`}
                onClick={() => setTheme(t.id)}
                aria-pressed={theme === t.id}
              >
                <span className="theme-swatch" aria-hidden="true">
                  {t.swatch.map((c, i) => (
                    <span key={i} style={{ background: c }} />
                  ))}
                </span>
                <span className="theme-text">
                  <span className="theme-name">{t.name}</span>
                  <span className="t-meta">{t.hint}</span>
                </span>
                <span className="theme-check" aria-hidden="true">
                  {theme === t.id ? '✓' : ''}
                </span>
              </button>
            </li>
          ))}
        </ul>

        <p className="t-meta" style={{ margin: 0 }}>
          ธีมเก็บไว้ในเครื่องนี้เท่านั้น เปลี่ยนแยกกันได้ในแต่ละอุปกรณ์
        </p>
      </div>
    </div>
  )
}
