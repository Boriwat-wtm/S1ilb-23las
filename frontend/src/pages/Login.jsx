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

  const switchMode = () => {
    setMode(isRegister ? 'login' : 'register')
    setError(null)
  }

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
    <main className="auth">
      {/* Out of the form's flow entirely. Changing the theme is not a step in
          signing in, and sitting in the tab order between the submit button
          and the mode switch implied that it was. */}
      <button
        type="button"
        className="btn btn-quiet btn-icon auth-theme"
        onClick={() => setThemeOpen(true)}
        aria-haspopup="dialog"
        title="เปลี่ยนธีมสี"
      >
        <Icon name="contrast" size={18} />
        <span className="sr-only">เปลี่ยนธีมสี</span>
      </button>

      <div className="auth-card">
        {/* The app never says what it is anywhere else — this is the only
            screen a first-time user sees before committing an account. */}
        <header className="auth-brand">
          <span className="auth-mark" aria-hidden="true">฿</span>
          <span className="auth-wordmark">Bank</span>
        </header>
        <p className="auth-tagline">
          สมุดรายรับ–รายจ่ายและยอดหนี้ แยกเป็นเล่ม
          <br />
          ทุกเล่มเป็นส่วนตัวจนกว่าคุณจะเชิญคนอื่นเอง
        </p>

        <form className="auth-form" onSubmit={submit}>
          {/* One heading, not a heading plus a tab strip saying the same word.
              The mode switch lives at the bottom as a link, which also stops
              two unequal-length Thai labels from splitting a segmented control
              a quarter of the way across. */}
          <h1 className="auth-title">{isRegister ? 'สร้างบัญชีใหม่' : 'เข้าสู่ระบบ'}</h1>

          <div className="auth-fields">
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
                <span className="field-hint">
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
                <span className="field-hint">ชื่อนี้จะขึ้นข้างรายการที่คุณลง</span>
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
              {isRegister && <span className="field-hint">อย่างน้อย 8 ตัว</span>}
            </label>
          </div>

          {error && (
            <p className="notice notice-error" role="alert">
              {error}
            </p>
          )}

          <button type="submit" className="btn btn-primary btn-block btn-lg" disabled={busy}>
            {busy ? 'กำลังดำเนินการ...' : isRegister ? 'สมัครและเข้าใช้' : 'เข้าสู่ระบบ'}
          </button>
        </form>

        <p className="auth-switch">
          {isRegister ? 'มีบัญชีอยู่แล้ว?' : 'ยังไม่มีบัญชี?'}{' '}
          <button type="button" className="link-btn" onClick={switchMode}>
            {isRegister ? 'เข้าสู่ระบบ' : 'สมัครใหม่'}
          </button>
        </p>
      </div>

      <ThemePicker open={themeOpen} onClose={() => setThemeOpen(false)} />
    </main>
  )
}
