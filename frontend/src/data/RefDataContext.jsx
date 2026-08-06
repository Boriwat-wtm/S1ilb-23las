import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { apiCategories, apiUsers } from '../api/client'
import { useAuth } from '../auth/AuthContext'

/** Categories and the two accounts barely ever change — fetch once per session. */
const RefDataContext = createContext({ categories: [], users: [], loading: true })

export function RefDataProvider({ children }) {
  const { user } = useAuth()
  const [categories, setCategories] = useState([])
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)

  const reload = useCallback(async () => {
    if (!user) return
    setLoading(true)
    try {
      const [cats, people] = await Promise.all([apiCategories(), apiUsers()])
      setCategories(cats)
      setUsers(people)
    } catch {
      // Non-fatal: the form still works, the dropdowns are just empty.
    } finally {
      setLoading(false)
    }
  }, [user])

  useEffect(() => {
    reload()
  }, [reload])

  const value = useMemo(
    () => ({ categories, users, loading, reload }),
    [categories, users, loading, reload],
  )
  return <RefDataContext.Provider value={value}>{children}</RefDataContext.Provider>
}

export const useRefData = () => useContext(RefDataContext)
