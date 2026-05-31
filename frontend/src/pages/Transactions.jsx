import React, { useEffect, useState } from 'react'
import { theme } from '../styles/theme'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'

const TYPE_LABELS = { expense: 'Витрата', income: 'Дохід', transfer: 'Переказ', debt_payment: 'Погашення боргу' }
const TYPE_COLORS = {
  expense: theme.colors.expense,
  income: theme.colors.income,
  transfer: theme.colors.accent,
  debt_payment: theme.colors.warning,
}

function TxRow({ tx }) {
  const color = TYPE_COLORS[tx.type] || theme.colors.text
  const sign = tx.type === 'income' ? '+' : '-'
  return (
    <div style={styles.row}>
      <div style={{ ...styles.typeBadge, backgroundColor: `${color}20`, color }}>
        {TYPE_LABELS[tx.type] || tx.type}
      </div>
      <div style={styles.desc}>{tx.description || '—'}</div>
      <div style={styles.date}>{new Date(tx.date).toLocaleDateString('uk-UA')}</div>
      <div style={{ ...styles.amount, color }}>
        {sign}{tx.amount.toLocaleString()} {tx.currency}
      </div>
    </div>
  )
}

export default function Transactions({ userId }) {
  const [transactions, setTransactions] = useState([])
  const [loading, setLoading] = useState(true)
  const [typeFilter, setTypeFilter] = useState('')

  const fetchTx = () => {
    const params = new URLSearchParams({ user_id: userId, limit: 100 })
    if (typeFilter) params.append('type', typeFilter)
    fetch(`${API}/transactions?${params}`)
      .then((r) => r.json())
      .then((data) => setTransactions(Array.isArray(data) ? data : []))
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchTx() }, [userId, typeFilter])

  return (
    <div>
      <h1 style={styles.title}>Транзакції</h1>

      <div style={styles.filters}>
        {['', 'expense', 'income', 'transfer'].map((t) => (
          <button
            key={t}
            onClick={() => setTypeFilter(t)}
            style={{
              ...styles.filterBtn,
              ...(typeFilter === t ? styles.filterBtnActive : {}),
            }}
          >
            {t ? TYPE_LABELS[t] : 'Всі'}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={styles.loading}>Завантаження...</div>
      ) : transactions.length === 0 ? (
        <div style={styles.empty}>Транзакцій не знайдено</div>
      ) : (
        <div style={styles.list}>
          <div style={styles.header}>
            <div style={styles.typeBadge}>Тип</div>
            <div style={styles.desc}>Опис</div>
            <div style={styles.date}>Дата</div>
            <div style={styles.amount}>Сума</div>
          </div>
          {transactions.map((tx) => <TxRow key={tx.id} tx={tx} />)}
        </div>
      )}
    </div>
  )
}

const styles = {
  title: { fontSize: theme.fontSizes['3xl'], fontWeight: '700', color: theme.colors.text, marginBottom: '24px' },
  loading: { color: theme.colors.textMuted, textAlign: 'center', paddingTop: '80px' },
  empty: { color: theme.colors.textMuted, textAlign: 'center', paddingTop: '80px' },
  filters: { display: 'flex', gap: '8px', marginBottom: '20px', flexWrap: 'wrap' },
  filterBtn: {
    padding: '8px 16px',
    borderRadius: theme.radii.full,
    border: `1px solid ${theme.colors.border}`,
    background: 'transparent',
    color: theme.colors.textMuted,
    cursor: 'pointer',
    fontSize: theme.fontSizes.sm,
    fontFamily: theme.fonts.base,
    transition: theme.transitions.fast,
  },
  filterBtnActive: {
    backgroundColor: theme.colors.accent,
    borderColor: theme.colors.accent,
    color: theme.colors.white,
  },
  list: {
    backgroundColor: theme.colors.surface,
    border: `1px solid ${theme.colors.border}`,
    borderRadius: theme.radii.lg,
    overflow: 'hidden',
  },
  header: {
    display: 'grid',
    gridTemplateColumns: '120px 1fr 100px 140px',
    padding: '12px 20px',
    borderBottom: `1px solid ${theme.colors.border}`,
    fontSize: theme.fontSizes.xs,
    color: theme.colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
  },
  row: {
    display: 'grid',
    gridTemplateColumns: '120px 1fr 100px 140px',
    padding: '14px 20px',
    borderBottom: `1px solid ${theme.colors.border}`,
    alignItems: 'center',
    transition: theme.transitions.fast,
  },
  typeBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    padding: '4px 10px',
    borderRadius: theme.radii.full,
    fontSize: theme.fontSizes.xs,
    fontWeight: '500',
    width: 'fit-content',
  },
  desc: { fontSize: theme.fontSizes.sm, color: theme.colors.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', paddingRight: '16px' },
  date: { fontSize: theme.fontSizes.sm, color: theme.colors.textMuted },
  amount: { fontSize: theme.fontSizes.sm, fontWeight: '600', textAlign: 'right' },
}
