import { useEffect, useRef, useState } from 'react'
import { apiHealth } from '../api/client'

/**
 * Render's free tier sleeps after 15 minutes idle and takes ~30-60s to come
 * back, and Neon autosuspends on top of that. Without something on screen the
 * first tap of the day just looks broken, so this owns that wait explicitly.
 *
 * The bar is honest about being an estimate: it eases toward 90% and only
 * completes when /health actually answers. It never sits at 100% waiting.
 */

const MESSAGES = [
  'กำลังปลุกเซิร์ฟเวอร์...',
  'เซิร์ฟเวอร์ฟรีมันหลับ ต้องรอสักครู่',
  'กำลังเชื่อมต่อฐานข้อมูล...',
  'ครั้งแรกของวันจะช้าหน่อย ครั้งต่อไปเร็วแล้ว',
  'เกือบได้แล้ว...',
  'ชงกาแฟรอได้เลย ☕',
]

const DB_WAKING_MESSAGE = 'เซิร์ฟเวอร์ตื่นแล้ว รอฐานข้อมูลอีกนิด...'
const SLOW_AFTER_MS = 75_000

export default function WakeScreen({ onReady }) {
  const [progress, setProgress] = useState(4)
  const [messageIndex, setMessageIndex] = useState(0)
  const [dbWaking, setDbWaking] = useState(false)
  const [tooSlow, setTooSlow] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const doneRef = useRef(false)

  // --- poll /health until the whole stack answers -------------------------
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
          // let the bar visibly finish before handing over
          setTimeout(onReady, 350)
          return
        }
        // Render is up but Neon is still waking — real progress, say so.
        setDbWaking(true)
        setProgress((p) => Math.max(p, 80))
      } catch {
        /* still asleep — keep waiting */
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

  // --- creeping bar, decelerating as it approaches 90 ---------------------
  useEffect(() => {
    const id = setInterval(() => {
      setProgress((p) => {
        if (p >= 90 || doneRef.current) return p
        const step = (90 - p) * 0.06 + Math.random() * 1.4
        return Math.min(90, p + step)
      })
    }, 420)
    return () => clearInterval(id)
  }, [attempt])

  // --- rotating copy ------------------------------------------------------
  useEffect(() => {
    const id = setInterval(() => setMessageIndex((i) => (i + 1) % MESSAGES.length), 2800)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const id = setTimeout(() => setTooSlow(true), SLOW_AFTER_MS)
    return () => clearTimeout(id)
  }, [attempt])

  const retry = () => {
    setTooSlow(false)
    setDbWaking(false)
    setProgress(4)
    setAttempt((a) => a + 1)
  }

  return (
    <div className="wake">
      <div className="wake-card">
        <div className="wake-logo" aria-hidden="true">฿</div>
        <h1 className="wake-title">Bank</h1>

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

        <p className="wake-message" aria-live="polite">
          {dbWaking ? DB_WAKING_MESSAGE : MESSAGES[messageIndex]}
        </p>

        {tooSlow && (
          <div className="wake-slow">
            <p>ใช้เวลานานกว่าปกติ — เซิร์ฟเวอร์อาจกำลังบูตอยู่</p>
            <button type="button" className="btn btn-ghost" onClick={retry}>
              ลองใหม่
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
