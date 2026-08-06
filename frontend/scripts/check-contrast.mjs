/**
 * WCAG contrast check across every theme in styles.css.
 *
 * Themes are the one part of this UI where a change that looks fine on the
 * author's screen can be unreadable on someone else's, and there are four of
 * them, so the palettes are checked rather than eyeballed. `--ink-3` is the
 * value that actually binds: it is the smallest, faintest text in the app.
 *
 * Run: npm run check:contrast
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const css = readFileSync(join(here, '..', 'src', 'styles.css'), 'utf8')

const luminance = (hex) => {
  const channel = (i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5)
}

const ratio = (a, b) => {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p)
  return (x + 0.05) / (y + 0.05)
}

const BLOCK =
  /(:root,\s*\[data-theme='ivory'\]|\[data-theme='(\w+)'\]|:root:not\(\[data-theme\]\),\s*\[data-theme='auto'\])\s*\{([\s\S]*?)\n\s*\}/g

const themes = new Map()
for (const match of css.matchAll(BLOCK)) {
  const name = match[2] ?? (match[1].includes('ivory') ? 'ivory' : 'auto (dark)')
  const tokens = Object.fromEntries(
    [...match[3].matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})/g)].map((m) => [m[1], m[2]]),
  )
  if (tokens.paper) themes.set(name, tokens)
}

// 4.5:1 is the AA floor for body text. The accent is never small text — it is
// links, focus rings and active borders — so it is held to the 3:1 non-text
// threshold instead of being given a free pass.
const PAIRS = [
  ['ink', 'paper', 4.5, 'body text'],
  ['ink-2', 'paper', 4.5, 'secondary text'],
  ['ink-3', 'paper', 4.5, 'faintest text'],
  ['ink-3', 'surface', 4.5, 'faintest on card'],
  ['credit', 'paper', 4.5, 'money in'],
  ['debit', 'paper', 4.5, 'money out'],
  ['credit', 'surface', 4.5, 'money in on card'],
  ['debit', 'surface', 4.5, 'money out on card'],
  ['accent', 'paper', 3.0, 'accent (non-text)'],
  ['btn-ink', 'btn-bg', 4.5, 'primary button'],
  ['danger', 'danger-soft', 4.5, 'error text'],
  ['warn', 'warn-soft', 4.5, 'warning text'],
]

let failures = 0
for (const [name, tokens] of themes) {
  console.log(`\n  ${name}`)
  for (const [fg, bg, min, label] of PAIRS) {
    if (!tokens[fg] || !tokens[bg]) continue
    const r = ratio(tokens[fg], tokens[bg])
    const ok = r >= min
    if (!ok) failures += 1
    console.log(
      `    ${ok ? 'ok  ' : 'FAIL'} ${r.toFixed(2).padStart(5)}:1  (min ${min})  ` +
        `${fg.padEnd(9)} on ${bg.padEnd(12)} ${label}`,
    )
  }
}

if (themes.size === 0) {
  console.error('\n  no themes parsed — did the [data-theme] blocks in styles.css change shape?')
  process.exit(1)
}

console.log(
  failures === 0
    ? `\n  PASS — ${themes.size} themes, every pair clears its threshold\n`
    : `\n  ${failures} pair(s) below threshold\n`,
)
process.exit(failures === 0 ? 0 : 1)
