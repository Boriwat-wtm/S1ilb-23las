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
export const THEMES = [
  {
    id: 'auto',
    name: 'ตามระบบ',
    hint: 'สลับสว่าง/มืดตามเครื่อง',
    swatch: ['#f8f6f1', '#0b0b0c', '#166b4a', '#c9a227'],
    paper: { light: '#f8f6f1', dark: '#0b0b0c' },
  },
  {
    id: 'ivory',
    name: 'Ivory',
    hint: 'กระดาษอุ่น หมึกดำ เขียวสน',
    swatch: ['#f8f6f1', '#191712', '#166b4a', '#a03c1f'],
    paper: '#f8f6f1',
  },
  {
    id: 'porcelain',
    name: 'Porcelain',
    hint: 'ขาวเย็น น้ำเงินเข้ม',
    swatch: ['#f5f7f9', '#12253b', '#0f6553', '#9e3229'],
    paper: '#f5f7f9',
  },
  {
    id: 'obsidian',
    name: 'Obsidian',
    hint: 'ดำสนิท ทองเหลือง',
    swatch: ['#0b0b0c', '#f2efe8', '#54c295', '#c9a227'],
    paper: '#0b0b0c',
  },
  {
    id: 'midnight',
    name: 'Midnight',
    hint: 'น้ำเงินลึก เงินเย็น',
    swatch: ['#080d16', '#e9eef7', '#4ec9a4', '#7aa7e0'],
    paper: '#080d16',
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
