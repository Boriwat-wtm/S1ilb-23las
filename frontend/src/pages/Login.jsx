import { useState } from 'react'

import Icon from '../components/Icon'
import ThemePicker from '../components/ThemePicker'
import { useAuth } from '../auth/AuthContext'

export default function Login() {
  const { login, register } = useAuth()
  const [themeOpen, setThemeOpen] = useState(false)
  const [mode, setMode] = useState('login')
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const isRegister = mode === 'register'

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      if (isRegister) await register(username, displayName, password)
      else await login(username, password)
    } catch (err) {
      setError(err.message || 'ไม่สำเร็จ')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="centered">
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-mark" aria-hidden="true">฿</div>
        <h1 className="t-display" style={{ fontSize: '1.5rem' }}>
          {isRegister ? 'สมัครใช้งาน' : 'เข้าสู่ระบบ'}
        </h1>

        <div className="segmented" role="group" aria-label="เลือกเข้าสู่ระบบหรือสมัคร">
          <button
            type="button"
            aria-pressed={!isRegister}
            onClick={() => {
              setMode('login')
              setError(null)
            }}
          >
            เข้าสู่ระบบ
          </button>
          <button
            type="button"
            aria-pressed={isRegister}
            onClick={() => {
              setMode('register')
              setError(null)
            }}
          >
            สมัครใหม่
          </button>
        </div>

        <label className="field">
          <span>ชื่อผู้ใช้</span>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck="false"
            required
          />
          {isRegister && (
            <span className="t-faint" style={{ fontSize: '0.74rem' }}>
              3–32 ตัว ใช้ a–z 0–9 . _ - เพื่อนจะเชิญคุณเข้าสมุดด้วยชื่อนี้
            </span>
          )}
        </label>

        {isRegister && (
          <label className="field">
            <span>ชื่อที่แสดง</span>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              autoComplete="name"
              required
            />
          </label>
        )}

        <label className="field">
          <span>รหัสผ่าน</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={isRegister ? 'new-password' : 'current-password'}
            required
          />
          {isRegister && (
            <span className="t-faint" style={{ fontSize: '0.74rem' }}>
              อย่างน้อย 8 ตัว
            </span>
          )}
        </label>

        {error && (
          <p className="notice notice-error" role="alert">
            {error}
          </p>
        )}

        <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
          {busy ? 'กำลังดำเนินการ...' : isRegister ? 'สมัครและเข้าใช้' : 'เข้าสู่ระบบ'}
        </button>

        {/* Available before signing in too — this is the first screen anyone
            sees, so it is the first place a theme is worth changing. */}
        <button
          type="button"
          className="btn btn-quiet btn-sm"
          onClick={() => setThemeOpen(true)}
          aria-haspopup="dialog"
        >
          <Icon name="contrast" size={16} />
          เปลี่ยนธีมสี
        </button>
      </form>

      <ThemePicker open={themeOpen} onClose={() => setThemeOpen(false)} />
    </main>
  )
}
