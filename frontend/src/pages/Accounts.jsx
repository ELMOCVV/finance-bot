import React, { useEffect, useState } from 'react'
import { theme } from '../styles/theme'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'

const CURRENCY_COLORS = { UAH: '#4caf82', USD: '#5557f5', USDT: '#f0a050', BTC: '#f7931a', ETH: '#627eea' }

function AccountCard({ account }) {
  const color = CURRENCY_COLORS[account.currency] || theme.colors.accent
  return (
    <div style={{ ...styles.card, borderLeft: `4px solid ${color}` }}>
      <div style={styles.cardTop}>
        <div style={styles.cardName}>{account.name}</div>
        {account.is_default && <span style={styles.defaultBadge}>За замовчуванням</span>}
      </div>
      <div style={{ ...styles.balance, color }}>
        {account.balance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        <span style={styles.currency}> {account.currency}</span>
      </div>
      {account.keywords?.length > 0 && (
        <div style={styles.keywords}>
          {account.keywords.map((kw) => (
            <span key={kw} style={styles.keyword}>{kw}</span>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Accounts({ userId }) {
  const [accounts, setAccounts] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API}/accounts?user_id=${userId}`)
      .then((r) => r.json())
      .then((data) => setAccounts(Array.isArray(data) ? data : []))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [userId])

  const totalUAH = accounts.reduce((sum, a) => sum + (a.currency === 'UAH' ? a.balance : 0), 0)

  return (
    <div>
      <div style={styles.header}>
        <h1 style={styles.title}>Рахунки</h1>
        <div style={styles.totalLabel}>
          Всього UAH: <span style={styles.totalValue}>{totalUAH.toLocaleString()} ₴</span>
        </div>
      </div>

      {loading ? (
        <div style={styles.loading}>Завантаження...</div>
      ) : accounts.length === 0 ? (
        <div style={styles.empty}>Рахунків немає. Додайте перший через Telegram-бота.</div>
      ) : (
        <div style={styles.grid}>
          {accounts.map((acc) => <AccountCard key={acc.id} account={acc} />)}
        </div>
      )}
    </div>
  )
}

const styles = {
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '24px' },
  title: { fontSize: theme.fontSizes['3xl'], fontWeight: '700', color: theme.colors.text },
  totalLabel: { fontSize: theme.fontSizes.sm, color: theme.colors.textMuted },
  totalValue: { color: theme.colors.text, fontWeight: '600' },
  loading: { color: theme.colors.textMuted, textAlign: 'center', paddingTop: '80px' },
  empty: { color: theme.colors.textMuted, textAlign: 'center', paddingTop: '80px' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '16px' },
  card: {
    backgroundColor: theme.colors.surface,
    border: `1px solid ${theme.colors.border}`,
    borderRadius: theme.radii.lg,
    padding: '20px',
    boxShadow: theme.shadows.sm,
  },
  cardTop: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' },
  cardName: { fontSize: theme.fontSizes.md, fontWeight: '600', color: theme.colors.text },
  defaultBadge: {
    fontSize: theme.fontSizes.xs,
    backgroundColor: theme.colors.accentLight,
    color: theme.colors.accent,
    padding: '2px 8px',
    borderRadius: theme.radii.full,
  },
  balance: { fontSize: theme.fontSizes['2xl'], fontWeight: '700', marginBottom: '12px' },
  currency: { fontSize: theme.fontSizes.md, fontWeight: '400', opacity: 0.8 },
  keywords: { display: 'flex', flexWrap: 'wrap', gap: '6px' },
  keyword: {
    fontSize: theme.fontSizes.xs,
    backgroundColor: theme.colors.surfaceHover,
    color: theme.colors.textMuted,
    padding: '2px 8px',
    borderRadius: theme.radii.full,
    border: `1px solid ${theme.colors.border}`,
  },
}
