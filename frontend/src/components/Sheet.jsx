import { useEffect, useRef, useState } from 'react'

import Icon from './Icon'

const EXIT_MS = 180

/**
 * Bottom sheet on phones, centred dialog from 640px.
 *
 * Extracted because the ledger switcher and the theme picker had grown
 * identical copies of the same focus-return, escape-to-close and
 * click-outside handling, and one of them was going to drift.
 *
 * It stays mounted for EXIT_MS after `open` goes false so the panel can
 * animate out. Exit animations driven off unmount tend to fight React; a small
 * explicit closing state does not.
 */
export default function Sheet({ open, onClose, title, label, children }) {
  const [mounted, setMounted] = useState(open)
  const [closing, setClosing] = useState(false)
  const panelRef = useRef(null)
  const returnFocusTo = useRef(null)

  useEffect(() => {
    if (open) {
      setMounted(true)
      setClosing(false)
      return undefined
    }
    if (!mounted) return undefined
    setClosing(true)
    const t = setTimeout(() => {
      setMounted(false)
      setClosing(false)
    }, EXIT_MS)
    return () => clearTimeout(t)
  }, [open, mounted])

  useEffect(() => {
    if (!open) return undefined

    returnFocusTo.current = document.activeElement
    panelRef.current?.querySelector('button, a, input, select')?.focus()

    // The page behind must not scroll under the sheet, or dismissing it can
    // land the reader somewhere they never navigated to.
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)

    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previousOverflow
      returnFocusTo.current?.focus?.()
    }
  }, [open, onClose])

  if (!mounted) return null

  return (
    <div
      className={`sheet-backdrop${closing ? ' closing' : ''}`}
      role="dialog"
      aria-modal="true"
      aria-label={label || title}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className={`sheet${closing ? ' closing' : ''}`} ref={panelRef}>
        <div className="sheet-grip" aria-hidden="true" />
        {title && (
          <div className="sheet-head">
            <h2 className="t-heading">{title}</h2>
            <button type="button" className="btn btn-quiet btn-icon" onClick={onClose}>
              <Icon name="close" size={18} />
              <span className="sr-only">ปิด</span>
            </button>
          </div>
        )}
        {children}
      </div>
    </div>
  )
}
