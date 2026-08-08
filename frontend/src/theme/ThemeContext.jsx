import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

const STORAGE_KEY = 'bank.theme'

/**
 * Themes are declared in styles.css under [data-theme]; this only decides
 * which attribute is on <html>. Keeping the palettes entirely in CSS means a
 * theme switch is one attribute write with no re-render and no flash.
 *
 * `paper` here is duplicated from the stylesheet for one narrow purpose: the
 * browser chrome colour on mobile, which cannot read a CSS variable. It is the
 * only place a colour is repeated, and it is the theme's --paper value.
 */
/**
 * Three, not four, and named for what they are rather than for minerals.
 *
 * The previous set — Ivory, Porcelain, Obsidian, Midnight — was four English
 * mineral names over four hue-rotations of the same palette, including
 * black-and-brass and navy-and-sky-blue, which are the two most generated
 * "premium" themes in existence. Each of these three is instead sampled from
 * something the app is actually about, and says so.
 */
export const THEMES = [
  {
    id: 'auto',
    name: 'ตามระบบ',
    hint: 'สลับสว่าง/มืดตามเครื่อง',
    swatch: ['#f2efe4', '#121110', '#245e46', '#8f3325'],
    paper: { light: '#f2efe4', dark: '#121110' },
  },
  {
    id: 'paper',
    name: 'กระดาษ',
    hint: 'สีสมุดบัญชีธนาคาร หมึกดำอุ่น แดงถอนเงิน',
    swatch: ['#f2efe4', '#1c1a13', '#245e46', '#8f3325'],
    paper: '#f2efe4',
  },
  {
    id: 'mono',
    name: 'ขาวดำ',
    hint: 'สีกระดาษสลิป มีสีเฉพาะตรงตัวเงิน',
    swatch: ['#ecebe8', '#131312', '#1d5f47', '#963224'],
    paper: '#ecebe8',
  },
  {
    id: 'night',
    name: 'กลางคืน',
    hint: 'ดำอมน้ำตาล ไม่ใช่น้ำเงิน',
    swatch: ['#121110', '#ebe8e1', '#6cbe95', '#d9866e'],
    paper: '#121110',
  },
]

const VALID = new Set(THEMES.map((t) => t.id))

function readStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return VALID.has(raw) ? raw : 'auto'
  } catch {
    return 'auto'
  }
}

const ThemeContext = createContext(null)

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(readStored)

  useEffect(() => {
    document.documentElement.dataset.theme = theme

    const meta = document.querySelector('meta[name="theme-color"]')
    if (!meta) return undefined

    const def = THEMES.find((t) => t.id === theme)
    if (typeof def?.paper === 'string') {
      meta.setAttribute('content', def.paper)
      return undefined
    }

    // Auto: track the OS while it is selected, so the status bar stays in step
    // when the phone flips to dark mode at sunset.
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const sync = () => meta.setAttribute('content', mq.matches ? def.paper.dark : def.paper.light)
    sync()
    mq.addEventListener('change', sync)
    return () => mq.removeEventListener('change', sync)
  }, [theme])

  const setTheme = useCallback((next) => {
    if (!VALID.has(next)) return
    setThemeState(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* private mode — the choice just won't survive a reload */
    }
  }, [])

  const value = useMemo(() => ({ theme, setTheme, themes: THEMES }), [theme, setTheme])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme ต้องอยู่ใน <ThemeProvider>')
  return ctx
}
