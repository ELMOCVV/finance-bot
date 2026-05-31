import React, { useEffect, useState } from 'react'
import { theme } from '../styles/theme'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'

function DebtCard({ debt }) {
  const paidPercent = debt.total_amount > 0
    ? ((debt.total_amount - debt.remaining_amount) / debt.total_amount * 100).toFixed(1)
    : 0
  const isUrgent = debt.next_payment_date && new Date(debt.next_payment_date) <= new Date(Date.now() + 7 * 86400000)

  return (
    <div style={{ ...styles.card, borderTop: `3px solid ${isUrgent ? theme.colors.danger : theme.colors.accent}` }}>
      <div style={styles.cardHeader}>
        <div style={styles.cardName}>{debt.name}</div>
        {isUrgent && <span style={styles.urgentBadge}>Скоро платіж</span>}
      </div>

      <div style={styles.amounts}>
        <div>
          <div style={styles.amountLabel}>Залишок</div>
          <div style={{ ...styles.amountValue, color: theme.colors.danger }}>
            {debt.remaining_amount.toLocaleString()} {debt.currency}
          </div>
        </div>
        <div>
          <div style={styles.amountLabel}>Щомісячний платіж</div>
          <div style={styles.amountValue}>{debt.monthly_payment.toLocaleString()} {debt.currency}</div>
        </div>
        <div>
          <div style={styles.amountLabel}>Ставка</div>
          <div style={styles.amountValue}>{debt.interest_rate}%</div>
        </div>
      </div>

      <div style={styles.progressSection}>
        <div style={styles.progressLabel}>
          <span>Погашено: {paidPercent}%</span>
          {debt.next_payment_date && (
            <span style={{ color: isUrgent ? theme.colors.danger : theme.colors.textMuted }}>
              Наступний платіж: {new Date(debt.next_payment_date).toLocaleDateString('uk-UA')}
            </span>
          )}
        </div>
        <div style={styles.progressBar}>
          <div style={{ ...styles.progressFill, width: `${paidPercent}%` }} />
        </div>
      </div>
    </div>
  )
}

export default function Debts({ userId }) {
  const [debts, setDebts] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API}/debts?user_id=${userId}`)
      .then((r) => r.json())
      .then((data) => setDebts(Array.isArray(data) ? data : []))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [userId])

  const totalRemaining = debts.reduce((sum, d) => sum + d.remaining_amount, 0)

  return (
    <div>
      <div style={styles.header}>
        <h1 style={styles.title}>Борги</h1>
        {debts.length > 0 && (
          <div style={styles.totalLabel}>
            Загалом: <span style={{ color: theme.colors.danger, fontWeight: '600' }}>{totalRemaining.toLocaleString()} UAH</span>
          </div>
        )}
      </div>

      {loading ? (
        <div style={styles.loading}>Завантаження...</div>
      ) : debts.length === 0 ? (
        <div style={styles.empty}>У вас немає активних боргів</div>
      ) : (
        <div style={styles.grid}>
          {debts.map((debt) => <DebtCard key={debt.id} debt={debt} />)}
        </div>
      )}
    </div>
  )
}

const styles = {
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '24px' },
  title: { fontSize: theme.fontSizes['3xl'], fontWeight: '700', color: theme.colors.text },
  totalLabel: { fontSize: theme.fontSizes.sm, color: theme.colors.textMuted },
  loading: { color: theme.colors.textMuted, textAlign: 'center', paddingTop: '80px' },
  empty: { color: theme.colors.textMuted, textAlign: 'center', paddingTop: '80px' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '16px' },
  card: {
    backgroundColor: theme.colors.surface,
    border: `1px solid ${theme.colors.border}`,
    borderRadius: theme.radii.lg,
    padding: '20px',
  },
  cardHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' },
  cardName: { fontSize: theme.fontSizes.lg, fontWeight: '600', color: theme.colors.text },
  urgentBadge: {
    fontSize: theme.fontSizes.xs,
    backgroundColor: `${theme.colors.danger}20`,
    color: theme.colors.danger,
    padding: '2px 8px',
    borderRadius: theme.radii.full,
  },
  amounts: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', marginBottom: '16px' },
  amountLabel: { fontSize: theme.fontSizes.xs, color: theme.colors.textMuted, marginBottom: '4px' },
  amountValue: { fontSize: theme.fontSizes.md, fontWeight: '600', color: theme.colors.text },
  progressSection: {},
  progressLabel: {
    display: 'flex',
    justifyContent: 'space-between',
    fontSize: theme.fontSizes.xs,
    color: theme.colors.textMuted,
    marginBottom: '6px',
  },
  progressBar: {
    height: '6px',
    backgroundColor: theme.colors.border,
    borderRadius: theme.radii.full,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radii.full,
    transition: theme.transitions.base,
  },
}
