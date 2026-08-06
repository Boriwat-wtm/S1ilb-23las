import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'

import { apiCategories, apiLedgers, getLastLedgerId, rememberLedgerId } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { ledgerWords } from '../utils/format'

/**
 * Holds the ledger list and which book is currently open.
 *
 * The selection is remembered across reloads because on a phone the app is
 * reopened dozens of times a day and landing on the wrong book — possibly a
 * shared one, in front of someone — is exactly the failure this app is
 * supposed to avoid.
 */
const LedgerContext = createContext(null)

export function LedgerProvider({ children }) {
  const { user } = useAuth()
  const [ledgers, setLedgers] = useState([])
  const [currentId, setCurrentId] = useState(() => getLastLedgerId())
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const reload = useCallback(async () => {
    if (!user) return
    setLoading(true)
    setError(null)
    try {
      const list = await apiLedgers()
      setLedgers(list)
      setCurrentId((prev) => {
        // A remembered id can be stale: the ledger may have been deleted, or
        // the caller removed from it. Fall back rather than 404 every request.
        if (prev && list.some((l) => l.id === prev)) return prev
        return list[0]?.id ?? null
      })
    } catch (err) {
      setError(err.message || 'โหลดรายการสมุดไม่สำเร็จ')
    } finally {
      setLoading(false)
    }
  }, [user])

  useEffect(() => {
    reload()
  }, [reload])

  const select = useCallback((id) => {
    setCurrentId(id)
    if (id) rememberLedgerId(id)
  }, [])

  useEffect(() => {
    if (currentId) rememberLedgerId(currentId)
  }, [currentId])

  const current = useMemo(
    () => ledgers.find((l) => l.id === currentId) ?? null,
    [ledgers, currentId],
  )

  // Categories belong to a ledger, so they are refetched whenever the open
  // book changes — never carried across.
  useEffect(() => {
    let cancelled = false
    if (!currentId) {
      setCategories([])
      return undefined
    }
    apiCategories(currentId)
      .then((cats) => {
        if (!cancelled) setCategories(cats)
      })
      .catch(() => {
        if (!cancelled) setCategories([])
      })
    return () => {
      cancelled = true
    }
  }, [currentId])

  const value = useMemo(
    () => ({
      ledgers,
      current,
      currentId,
      categories,
      loading,
      error,
      select,
      reload,
      words: ledgerWords(current?.kind),
      canEdit: current ? current.my_role !== 'viewer' : false,
      isOwner: current ? current.my_role === 'owner' : false,
    }),
    [ledgers, current, currentId, categories, loading, error, select, reload],
  )

  return <LedgerContext.Provider value={value}>{children}</LedgerContext.Provider>
}

export function useLedgers() {
  const ctx = useContext(LedgerContext)
  if (!ctx) throw new Error('useLedgers ต้องอยู่ใน <LedgerProvider>')
  return ctx
}
