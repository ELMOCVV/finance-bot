import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchTransactions } from '../api/queries'
import { SkeletonList } from '../components/Skeleton'

const TX_ICONS  = { expense: '➖', income: '➕', transfer: '🔄', debt_payment: '💳' }
const TX_LABELS = { expense: 'Витрата', income: 'Дохід', transfer: 'Переказ', debt_payment: 'Борг' }
const FILTERS = [
  { key: '', label: 'Все' },
  { key: 'expense', label: 'Витрата' },
  { key: 'income', label: 'Дохід' },
  { key: 'transfer', label: 'Переказ' },
]

function formatDate(dateStr) {
  const d = new Date(dateStr)
  return d.toLocaleDateString('uk-UA', { day: 'numeric', month: 'long', year: 'numeric' })
}

function groupByDate(txns) {
  const groups = {}
  for (const tx of txns) {
    const key = (tx.date || '').split('T')[0]
    if (!groups[key]) groups[key] = []
    groups[key].push(tx)
  }
  return Object.entries(groups).sort(([a], [b]) => b.localeCompare(a))
}

export default function Transactions({ userId }) {
  const [filter, setFilter] = useState('')
  const [search, setSearch] = useState('')

  const { data, isLoading, isError } = useQuery({
    queryKey: ['transactions', userId, filter],
    queryFn: () => fetchTransactions(userId, filter ? { type: filter } : {}),
    staleTime: 60_000,
  })

  const filtered = useMemo(() => {
    const txns = data || []
    if (!search.trim()) return txns
    const q = search.toLowerCase()
    return txns.filter((tx) => (tx.description || '').toLowerCase().includes(q))
  }, [data, search])

  const groups = useMemo(() => groupByDate(filtered), [filtered])

  return (
    <div>
      <div className="page-header">
        <div className="page-title">Транзакції</div>
      </div>

      <div className="filter-row">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            className={`chip${filter === f.key ? ' active' : ''}`}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="search-wrap">
        <input
          className="search-input"
          type="text"
          placeholder="Пошук по опису..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {isLoading ? (
        <SkeletonList rows={6} />
      ) : isError ? (
        <div className="error-msg">Помилка завантаження транзакцій</div>
      ) : groups.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">💸</div>
          <div className="empty-text">
            {search ? 'Нічого не знайдено' : 'Транзакцій ще немає.\nДодай першу через бота!'}
          </div>
        </div>
      ) : (
        groups.map(([date, txns]) => (
          <div key={date} className="date-group">
            <div className="date-heading">{formatDate(date)}</div>
            {txns.map((tx) => (
              <div key={tx.id} className="tx-item">
                <div className={`tx-icon ${tx.type}`}>
                  {TX_ICONS[tx.type] || '💸'}
                </div>
                <div className="tx-body">
                  <div className="tx-desc">{tx.description || TX_LABELS[tx.type] || 'Транзакція'}</div>
                  <div className="tx-meta">
                    {tx.currency !== 'UAH' && `${tx.amount.toLocaleString('uk-UA')} ${tx.currency} · `}
                    {new Date(tx.date).toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit' })}
                  </div>
                </div>
                <div className={`tx-amount ${tx.type}`}>
                  {tx.type === 'income' ? '+' : tx.type === 'expense' ? '-' : ''}
                  {Math.round(tx.amount_uah || tx.amount).toLocaleString('uk-UA')} ₴
                </div>
              </div>
            ))}
          </div>
        ))
      )}
    </div>
  )
}
