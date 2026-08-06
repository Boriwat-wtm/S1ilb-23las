import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

import {
  apiChangePassword,
  apiLogin,
  apiRegister,
  apiUpdateProfile,
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

  const updateProfile = useCallback(async (displayName) => {
    const updated = await apiUpdateProfile(displayName.trim())
    // The stored copy feeds the topbar on the next cold start, so it has to
    // move with the server's answer, not with what was typed.
    storeSession(getToken(), updated)
    setUser(updated)
    return updated
  }, [])

  // Changing the password revokes every token, including this tab's. The
  // server hands back a fresh one so the device doing the change stays in.
  const changePassword = useCallback(
    async (currentPassword, newPassword) => adopt(await apiChangePassword(currentPassword, newPassword)),
    [adopt],
  )

  const value = useMemo(
    () => ({ user, login, register, logout, updateProfile, changePassword }),
    [user, login, register, logout, updateProfile, changePassword],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth ต้องอยู่ใน <AuthProvider>')
  return ctx
}
