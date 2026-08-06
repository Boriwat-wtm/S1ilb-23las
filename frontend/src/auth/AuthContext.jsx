import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import {
  apiLogin,
  clearSession,
  getStoredUser,
  getToken,
  setUnauthorizedHandler,
  storeSession,
} from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => (getToken() ? getStoredUser() : null))

  const logout = useCallback(() => {
    clearSession()
    setUser(null)
  }, [])

  // Any 401 anywhere — expired token, or iOS evicting a standalone PWA's
  // localStorage — drops straight back to the login screen.
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null))
    return () => setUnauthorizedHandler(() => {})
  }, [])

  const login = useCallback(async (username, password) => {
    const res = await apiLogin(username, password)
    storeSession(res.access_token, res.user)
    setUser(res.user)
    return res.user
  }, [])

  const value = useMemo(() => ({ user, login, logout }), [user, login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth ต้องอยู่ใน <AuthProvider>')
  return ctx
}
