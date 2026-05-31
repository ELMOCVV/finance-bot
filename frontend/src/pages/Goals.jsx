import React, { useEffect, useState } from 'react'
import { theme } from '../styles/theme'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'

function GoalCard({ goal }) {
  const pct = Math.min(goal.progress_percent, 100)
  const daysLeft = goal.deadline
    ? Math.ceil((new Date(goal.deadline) - Date.now()) / 86400000)
    : null
  const isCompleted = pct >= 100
  const accentColor = isCompleted ? theme.colors.success : theme.colors.accent

  return (
    <div style={{ ...styles.card, opacity: isCompleted ? 0.85 : 1 }}>
      <div style={styles.cardHeader}>
        <div style={styles.cardName}>{goal.name}</div>
        {isCompleted && <span style={styles.doneBadge}>Виконано</span>}
      </div>

      <div style={styles.amounts}>
        <span style={{ ...styles.current, color: accentColor }}>
          {goal.current_amount.toLocaleString()} {goal.currency}
        </span>
        <span style={styles.separator}>/</span>
        <span style={styles.target}>{goal.target_amount.toLocaleString()} {goal.currency}</span>
      </div>

      <div style={styles.progressBar}>
        <div style={{ ...styles.progressFill, width: `${pct}%`, backgroundColor: accentColor }} />
      </div>

      <div style={styles.footer}>
        <span style={styles.pct}>{pct}%</span>
        {daysLeft !== null && (
          <span style={{ color: daysLeft < 30 ? theme.colors.warning : theme.colors.textMuted, fontSize: theme.fontSizes.xs }}>
            {daysLeft > 0 ? `${daysLeft} днів` : 'Термін минув'}
          </span>
        )}
      </div>
    </div>
  )
}

export default function Goals({ userId }) {
  const [goals, setGoals] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API}/goals?user_id=${userId}`)
      .then((r) => r.json())
      .then((data) => setGoals(Array.isArray(data) ? data : []))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [userId])

  return (
    <div>
      <h1 style={styles.title}>Фінансові цілі</h1>

      {loading ? (
        <div style={styles.loading}>Завантаження...</div>
      ) : goals.length === 0 ? (
        <div style={styles.empty}>У вас ще немає фінансових цілей</div>
      ) : (
        <div style={styles.grid}>
          {goals.map((goal) => <GoalCard key={goal.id} goal={goal} />)}
        </div>
      )}
    </div>
  )
}

const styles = {
  title: { fontSize: theme.fontSizes['3xl'], fontWeight: '700', color: theme.colors.text, marginBottom: '24px' },
  loading: { color: theme.colors.textMuted, textAlign: 'center', paddingTop: '80px' },
  empty: { color: theme.colors.textMuted, textAlign: 'center', paddingTop: '80px' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '16px' },
  card: {
    backgroundColor: theme.colors.surface,
    border: `1px solid ${theme.colors.border}`,
    borderRadius: theme.radii.lg,
    padding: '20px',
    boxShadow: theme.shadows.sm,
  },
  cardHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' },
  cardName: { fontSize: theme.fontSizes.md, fontWeight: '600', color: theme.colors.text },
  doneBadge: {
    fontSize: theme.fontSizes.xs,
    backgroundColor: `${theme.colors.success}20`,
    color: theme.colors.success,
    padding: '2px 8px',
    borderRadius: theme.radii.full,
  },
  amounts: { display: 'flex', alignItems: 'baseline', gap: '6px', marginBottom: '10px' },
  current: { fontSize: theme.fontSizes.xl, fontWeight: '700' },
  separator: { color: theme.colors.textDim, fontSize: theme.fontSizes.lg },
  target: { color: theme.colors.textMuted, fontSize: theme.fontSizes.md },
  progressBar: {
    height: '8px',
    backgroundColor: theme.colors.border,
    borderRadius: theme.radii.full,
    overflow: 'hidden',
    marginBottom: '8px',
  },
  progressFill: {
    height: '100%',
    borderRadius: theme.radii.full,
    transition: theme.transitions.base,
  },
  footer: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  pct: { fontSize: theme.fontSizes.sm, color: theme.colors.textMuted, fontWeight: '500' },
}
