import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

import {
  apiLogin,
  apiRegister,
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
  // localStorage — drops straight back to the sign-in screen.
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null))
    return () => setUnauthorizedHandler(() => {})
  }, [])

  const adopt = useCallback((res) => {
    storeSession(res.access_token, res.user)
    setUser(res.user)
    return res.user
  }, [])

  const login = useCallback(
    async (username, password) => adopt(await apiLogin(username.trim().toLowerCase(), password)),
    [adopt],
  )

  const register = useCallback(
    async (username, displayName, password) =>
      adopt(await apiRegister(username.trim().toLowerCase(), displayName.trim(), password)),
    [adopt],
  )

  const value = useMemo(
    () => ({ user, login, register, logout }),
    [user, login, register, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth ต้องอยู่ใน <AuthProvider>')
  return ctx
}
