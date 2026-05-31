import React, { useEffect, useState } from 'react'
import { theme } from '../styles/theme'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'

function StatCard({ label, value, color, icon }) {
  return (
    <div style={{ ...styles.card, borderTop: `3px solid ${color}` }}>
      <div style={styles.cardIcon}>{icon}</div>
      <div style={{ ...styles.cardValue, color }}>{value}</div>
      <div style={styles.cardLabel}>{label}</div>
    </div>
  )
}

function CategoryBar({ name, icon, total, maxTotal, color }) {
  const pct = maxTotal > 0 ? (total / maxTotal) * 100 : 0
  return (
    <div style={styles.catRow}>
      <div style={styles.catInfo}>
        <span>{icon}</span>
        <span style={styles.catName}>{name}</span>
      </div>
      <div style={styles.catBarWrap}>
        <div style={{ ...styles.catBar, width: `${pct}%`, backgroundColor: color || theme.colors.accent }} />
      </div>
      <span style={styles.catAmount}>{total.toLocaleString()} ₴</span>
    </div>
  )
}

export default function Dashboard({ userId }) {
  const [summary, setSummary] = useState(null)
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [month] = useState(() => {
    const now = new Date()
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  })

  useEffect(() => {
    const params = `user_id=${userId}&month=${month}`
    Promise.all([
      fetch(`${API}/analytics/summary?${params}`).then((r) => r.json()),
      fetch(`${API}/analytics/by-category?${params}`).then((r) => r.json()),
    ])
      .then(([s, c]) => {
        setSummary(s)
        setCategories(Array.isArray(c) ? c : [])
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [userId, month])

  if (loading) return <div style={styles.loading}>Завантаження...</div>

  const maxCat = categories.length ? Math.max(...categories.map((c) => c.total_uah)) : 0

  return (
    <div>
      <h1 style={styles.title}>Dashboard</h1>
      <p style={styles.subtitle}>{month}</p>

      <div style={styles.statsGrid}>
        <StatCard
          label="Доходи"
          value={`${(summary?.total_income_uah ?? 0).toLocaleString()} ₴`}
          color={theme.colors.income}
          icon="➕"
        />
        <StatCard
          label="Витрати"
          value={`${(summary?.total_expense_uah ?? 0).toLocaleString()} ₴`}
          color={theme.colors.expense}
          icon="➖"
        />
        <StatCard
          label="Чистий результат"
          value={`${(summary?.net_uah ?? 0).toLocaleString()} ₴`}
          color={summary?.net_uah >= 0 ? theme.colors.income : theme.colors.expense}
          icon="💰"
        />
      </div>

      {/* Рахунки */}
      {summary?.accounts?.length > 0 && (
        <div style={styles.section}>
          <h2 style={styles.sectionTitle}>Рахунки</h2>
          <div style={styles.accountsGrid}>
            {summary.accounts.map((acc) => (
              <div key={acc.id} style={styles.accountCard}>
                <div style={styles.accountName}>{acc.name}</div>
                <div style={styles.accountBalance}>
                  {acc.balance.toLocaleString()} {acc.currency}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Витрати по категоріях */}
      {categories.length > 0 && (
        <div style={styles.section}>
          <h2 style={styles.sectionTitle}>Витрати по категоріях</h2>
          <div style={styles.card}>
            {categories.map((cat) => (
              <CategoryBar
                key={cat.category_id}
                name={cat.name}
                icon={cat.icon}
                total={cat.total_uah}
                maxTotal={maxCat}
                color={cat.color}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

const styles = {
  title: { fontSize: theme.fontSizes['3xl'], fontWeight: '700', color: theme.colors.text },
  subtitle: { color: theme.colors.textMuted, marginTop: '4px', marginBottom: '24px' },
  loading: { color: theme.colors.textMuted, textAlign: 'center', paddingTop: '80px' },
  statsGrid: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginBottom: '32px' },
  card: {
    backgroundColor: theme.colors.surface,
    border: `1px solid ${theme.colors.border}`,
    borderRadius: theme.radii.lg,
    padding: '20px',
    boxShadow: theme.shadows.sm,
  },
  cardIcon: { fontSize: '24px', marginBottom: '8px' },
  cardValue: { fontSize: theme.fontSizes['2xl'], fontWeight: '700', marginBottom: '4px' },
  cardLabel: { fontSize: theme.fontSizes.sm, color: theme.colors.textMuted },
  section: { marginBottom: '32px' },
  sectionTitle: { fontSize: theme.fontSizes.xl, fontWeight: '600', marginBottom: '16px', color: theme.colors.text },
  accountsGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '12px' },
  accountCard: {
    backgroundColor: theme.colors.surface,
    border: `1px solid ${theme.colors.border}`,
    borderRadius: theme.radii.md,
    padding: '16px',
  },
  accountName: { fontSize: theme.fontSizes.sm, color: theme.colors.textMuted, marginBottom: '6px' },
  accountBalance: { fontSize: theme.fontSizes.lg, fontWeight: '600', color: theme.colors.text },
  catRow: { display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' },
  catInfo: { display: 'flex', gap: '8px', width: '140px', flexShrink: 0 },
  catName: { fontSize: theme.fontSizes.sm, color: theme.colors.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  catBarWrap: { flex: 1, backgroundColor: theme.colors.border, borderRadius: theme.radii.full, height: '8px', overflow: 'hidden' },
  catBar: { height: '100%', borderRadius: theme.radii.full, transition: theme.transitions.base },
  catAmount: { fontSize: theme.fontSizes.sm, color: theme.colors.textMuted, width: '80px', textAlign: 'right', flexShrink: 0 },
}
