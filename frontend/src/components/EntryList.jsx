import { Link } from 'react-router-dom'

import Icon from './Icon'
import Money from './Money'
import { dayKey, entryEffect, fmtDayFull, fmtTime } from '../utils/format'

/** The comfortable view: one line per entry, grouped under a ruled day bar
 *  carrying that day's net. Same data as the table, less of it at once. */
export default function EntryList({ entries }) {
  const days = []
  const index = new Map()
  for (const entry of entries) {
    const key = dayKey(entry.occurred_at)
    if (!index.has(key)) {
      const group = { key, date: entry.occurred_at, items: [], net: 0 }
      index.set(key, group)
      days.push(group)
    }
    const group = index.get(key)
    group.items.push(entry)
    group.net += entryEffect(entry)
  }

  return (
    <div className="stack">
      {days.map((day) => (
        <section key={day.key} className="day-group">
          <header className="day-bar">
            <span>{fmtDayFull(day.date)}</span>
            <Money value={day.net} />
          </header>
          <ul className="entry-list">
            {day.items.map((e) => (
              <li key={e.id}>
                <Link to={`/entry/${e.id}`} className="entry-row">
                  <span className="entry-glyph">
                    {e.category?.emoji ? (
                      <span className="glyph-emoji" aria-hidden="true">
                        {e.category.emoji}
                      </span>
                    ) : (
                      <Icon name={e.direction === 'in' ? 'arrowIn' : 'arrowOut'} size={18} />
                    )}
                  </span>
                  <span className="entry-main">
                    <span className="entry-desc">
                      {e.description}
                      {e.slip_path && (
                        <Icon name="paperclip" size={13} className="entry-clip" />
                      )}
                    </span>
                    <span className="entry-meta">
                      {e.category?.name || 'ไม่ระบุหมวด'} · {e.created_by.display_name} ·{' '}
                      {fmtTime(e.occurred_at)}
                    </span>
                  </span>
                  <Money value={e.amount} direction={e.direction} />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}
