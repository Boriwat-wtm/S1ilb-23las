import { useEffect, useRef, useState } from 'react'

import { apiHealth } from '../api/client'

/**
 * Render's free tier sleeps after 15 minutes idle and takes ~30-60s to return,
 * and Neon autosuspends on top of that. Without something on screen, the first
 * tap of the day just looks broken.
 *
 * The bar is honest about being an estimate: it eases toward 90% and only
 * completes when /health actually answers, so it never sits at 100% lying.
 */

const MESSAGES = [
  'กำลังปลุกเซิร์ฟเวอร์...',
  'เซิร์ฟเวอร์ฟรีมันหลับ ต้องรอสักครู่',
  'กำลังเชื่อมต่อฐานข้อมูล...',
  'ครั้งแรกของวันจะช้าหน่อย ครั้งต่อไปเร็วแล้ว',
  'เกือบได้แล้ว...',
]

const DB_WAKING = 'เซิร์ฟเวอร์ตื่นแล้ว รอฐานข้อมูลอีกนิด...'
const SLOW_AFTER_MS = 75_000

export default function WakeScreen({ onReady }) {
  const [progress, setProgress] = useState(4)
  const [messageIndex, setMessageIndex] = useState(0)
  const [dbWaking, setDbWaking] = useState(false)
  const [tooSlow, setTooSlow] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const doneRef = useRef(false)

  useEffect(() => {
    doneRef.current = false
    const controller = new AbortController()
    let timer

    const poll = async () => {
      if (doneRef.current) return
      try {
        const health = await apiHealth(controller.signal)
        if (doneRef.current) return
        if (health?.database === 'ok') {
          doneRef.current = true
          setProgress(100)
          setTimeout(onReady, 320) // let the bar visibly finish
          return
        }
        // Render answered but Neon has not — real progress, so say so.
        setDbWaking(true)
        setProgress((p) => Math.max(p, 80))
      } catch {
        /* still asleep */
      }
      timer = setTimeout(poll, 2000)
    }

    poll()
    return () => {
      doneRef.current = true
      controller.abort()
      clearTimeout(timer)
    }
  }, [onReady, attempt])

  useEffect(() => {
    const id = setInterval(() => {
      setProgress((p) => {
        if (p >= 90 || doneRef.current) return p
        return Math.min(90, p + (90 - p) * 0.06 + Math.random() * 1.4)
      })
    }, 420)
    return () => clearInterval(id)
  }, [attempt])

  useEffect(() => {
    const id = setInterval(() => setMessageIndex((i) => (i + 1) % MESSAGES.length), 2800)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const id = setTimeout(() => setTooSlow(true), SLOW_AFTER_MS)
    return () => clearTimeout(id)
  }, [attempt])

  return (
    <main className="auth">
      <div className="auth-card wake-card">
        <header className="auth-brand">
          <span className="auth-mark" aria-hidden="true">฿</span>
          <span className="auth-wordmark">Bank</span>
        </header>

        <div
          className="wake-bar"
          role="progressbar"
          aria-valuenow={Math.round(progress)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="กำลังเชื่อมต่อเซิร์ฟเวอร์"
        >
          <div className="wake-bar-fill" style={{ width: `${progress}%` }} />
        </div>

        <p className="wake-msg" aria-live="polite">
          {dbWaking ? DB_WAKING : MESSAGES[messageIndex]}
        </p>

        {tooSlow && (
          <div className="notice notice-warn">
            <p>ใช้เวลานานกว่าปกติ — เซิร์ฟเวอร์อาจกำลังบูตอยู่</p>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => {
                setTooSlow(false)
                setDbWaking(false)
                setProgress(4)
                setAttempt((a) => a + 1)
              }}
            >
              ลองใหม่
            </button>
          </div>
        )}
      </div>
    </main>
  )
}
