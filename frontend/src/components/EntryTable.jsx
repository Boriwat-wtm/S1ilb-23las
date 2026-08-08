import { Link } from 'react-router-dom'

import Icon from './Icon'
import Money from './Money'
import { dayKey, fmtDateShort, withRunningBalance } from '../utils/format'

/**
 * The table is the reason this looks like an account book rather than a feed.
 *
 * The column that earns it is the last one. `withRunningBalance` anchors to the
 * server's exact total for the current filter and walks backwards down the
 * newest-first rows, so it stays correct for any prefix — which matters,
 * because pagination means we normally hold only a prefix. It is labelled
 * "สะสม" and not "คงเหลือ" because with a month filter on, it is the running
 * total *within that filter*, not the lifetime balance.
 *
 * Dates repeat down a ledger, so each one is shown once per day and hidden
 * (not removed — the cell keeps its width and the text stays selectable) on
 * the rows below it. That produces day grouping without adding an element.
 */
export default function EntryTable({ entries, filterBalance, words, showRunning = true }) {
  const rows = withRunningBalance(entries, filterBalance)

  return (
    <div className="table-scroll">
      <table className="ledger">
        <caption className="sr-only">
          รายการทั้งหมดในมุมมองตาราง เรียงจากใหม่ไปเก่า
        </caption>
        <thead>
          <tr>
            <th scope="col">วันที่</th>
            <th scope="col">รายการ</th>
            <th scope="col">หมวดหมู่</th>
            <th scope="col">คนลง</th>
            <th scope="col" className="right">{words.in}</th>
            <th scope="col" className="right">{words.out}</th>
            {showRunning && (
              <th scope="col" className="right">สะสม</th>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((e, i) => {
            const sameDayAsAbove = i > 0 && dayKey(e.occurred_at) === dayKey(rows[i - 1].occurred_at)
            return (
              <tr key={e.id}>
                <td className={`date-cell num${sameDayAsAbove ? ' repeat' : ''}`}>
                  {fmtDateShort(e.occurred_at)}
                </td>
                <td className="desc-cell">
                  <Link to={`/entry/${e.id}`}>{e.description}</Link>
                  {e.slip_path && (
                    <Icon
                      name="paperclip"
                      size={13}
                      className="entry-clip"
                      role="img"
                      aria-hidden={undefined}
                      aria-label="มีสลิปแนบ"
                    />
                  )}
                  {e.note && <div className="t-meta">{e.note}</div>}
                </td>
                <td className="t-dim">
                  {e.category ? `${e.category.emoji || ''} ${e.category.name}`.trim() : '—'}
                </td>
                <td className="t-dim">{e.created_by.display_name}</td>
                <td className="right num">
                  {e.direction === 'in' ? <Money value={e.amount} direction="in" /> : ''}
                </td>
                <td className="right num">
                  {e.direction === 'out' ? <Money value={e.amount} direction="out" /> : ''}
                </td>
                {showRunning && (
                  <td className="right num running">
                    <Money value={e.running} signed={false} className="t-dim" />
                  </td>
                )}
              </tr>
            )
          })}
          {rows.length === 0 && (
            <tr>
              <td colSpan={showRunning ? 7 : 6} className="t-faint" style={{ textAlign: 'center', padding: '32px' }}>
                ไม่มีรายการ
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {showRunning && rows.length > 0 && (
        <p className="table-note">
          คอลัมน์ “สะสม” คือยอดสะสมภายในตัวกรองที่เลือกอยู่ ไม่ใช่ยอดตลอดอายุสมุด
        </p>
      )}
    </div>
  )
}
