export function Skeleton({ h = 20, w = '100%', style = {} }) {
  return (
    <div
      className="skeleton"
      style={{ height: h, width: w, ...style }}
    />
  )
}

export function SkeletonCard({ lines = 2 }) {
  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} h={i === 0 ? 16 : 28} w={i === 0 ? '50%' : '80%'} />
      ))}
    </div>
  )
}

export function SkeletonList({ rows = 4 }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '0 16px' }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height: 60, borderRadius: 'var(--radius-sm)' }} />
      ))}
    </div>
  )
}
