import Icon from './Icon'
import Sheet from './Sheet'
import { useTheme } from '../theme/ThemeContext'

/**
 * Each option shows the theme's actual four colours — paper, ink, credit,
 * accent — rather than a name and a moon icon. Picking applies immediately
 * with the sheet still open, so the choice is judged against the real
 * interface behind it instead of a swatch.
 */
export function ThemeOptions() {
  const { theme, setTheme, themes } = useTheme()
  return (
    <ul className="theme-list">
      {themes.map((t) => (
        <li key={t.id}>
          <button
            type="button"
            className={`theme-option${theme === t.id ? ' active' : ''}`}
            onClick={() => setTheme(t.id)}
            aria-pressed={theme === t.id}
          >
            <span className="theme-swatch" aria-hidden="true">
              {t.swatch.map((c, i) => (
                <span key={i} style={{ background: c }} />
              ))}
            </span>
            <span className="theme-text">
              <span className="theme-name">{t.name}</span>
              <span className="t-meta">{t.hint}</span>
            </span>
            <span className="theme-check">
              {theme === t.id && <Icon name="check" size={17} />}
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}

export default function ThemePicker({ open, onClose }) {
  return (
    <Sheet open={open} onClose={onClose} title="ธีมสี" label="เลือกธีม">
      <ThemeOptions />
      <p className="t-meta" style={{ margin: 0 }}>
        ธีมเก็บไว้ในเครื่องนี้เท่านั้น เปลี่ยนแยกกันได้ในแต่ละอุปกรณ์
      </p>
    </Sheet>
  )
}
