/**
 * Row-shaped placeholders instead of the word "loading".
 *
 * Render's free tier means the first request of the day is genuinely slow, so
 * this is not decoration: showing the shape of what is arriving reads as
 * progress, where a line of centred grey text reads as a stall.
 *
 * `aria-hidden` with a live-region label above it, so a screen reader hears
 * "กำลังโหลด" once rather than a stream of empty rows.
 */
export default function SkeletonRows({ rows = 6, label = 'กำลังโหลดรายการ' }) {
  return (
    <div className="skeleton-rows">
      <span className="sr-only" role="status">
        {label}
      </span>
      {Array.from({ length: rows }, (_, i) => (
        <div className="skeleton-row" key={i} aria-hidden="true">
          <span className="skeleton" />
          <span>
            {/* Widths vary so the block reads as text, not as a barcode. */}
            <span
              className="skeleton skeleton-line"
              style={{ display: 'block', width: `${52 + ((i * 13) % 34)}%` }}
            />
            <span
              className="skeleton skeleton-line"
              style={{ display: 'block', width: `${30 + ((i * 7) % 22)}%` }}
            />
          </span>
          <span className="skeleton skeleton-amount" />
        </div>
      ))}
    </div>
  )
}
