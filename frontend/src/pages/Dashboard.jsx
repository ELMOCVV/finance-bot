import { useQueries } from '@tanstack/react-query'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'
import { fetchAccounts, fetchAnalyticsSummary, fetchAnalyticsByCategory, fetchGoals, fetchDebts, fetchTransactions } from '../api/queries'
import { useExchangeRates, toUAH, fmtUAH, fmtAmount } from '../api/rates'
import { currentMonth } from '../hooks/useTelegramUser'
import { SkeletonCard, SkeletonList, Skeleton } from '../components/Skeleton'

const CURRENCY_FLAGS = { UAH: '🇺🇦', USD: '🇺🇸', USDT: '💵', EUR: '🇪🇺', BTC: '₿', ETH: 'Ξ' }
const PIE_COLORS = ['#5557f5', '#10b981', '#f59e0b', '#f43f5e', '#8b5cf6', '#06b6d4']

function buildExpenseChartData(transactions) {
  const days = 30
  const result = {}
  const now = new Date()
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(now)
    d.setDate(d.getDate() - i)
    result[d.toISOString().split('T')[0]] = 0
  }
  for (const tx of transactions) {
    const key = (tx.date || '').split('T')[0]
    if (key in result) result[key] += tx.amount_uah || 0
  }
  return Object.entries(result).map(([date, amount]) => ({
    day: date.slice(5).replace('-', '/'),
    amount: Math.round(amount),
  }))
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 12px', fontSize: 13 }}>
      <div style={{ color: 'var(--text-muted)', marginBottom: 2 }}>{label}</div>
      <div style={{ color: 'var(--accent)', fontWeight: 700 }}>{fmtUAH(payload[0].value)}</div>
    </div>
  )
}

export default function Dashboard({ userId }) {
  const month = currentMonth()
  const { data: rates } = useExchangeRates()

  const results = useQueries({
    queries: [
      { queryKey: ['accounts', userId],           queryFn: () => fetchAccounts(userId),                   staleTime: 60_000 },
      { queryKey: ['summary', userId, month],      queryFn: () => fetchAnalyticsSummary(userId, month),    staleTime: 60_000 },
      { queryKey: ['by-category', userId, month],  queryFn: () => fetchAnalyticsByCategory(userId, month), staleTime: 60_000 },
      { queryKey: ['goals', userId],               queryFn: () => fetchGoals(userId),                      staleTime: 60_000 },
      { queryKey: ['debts', userId],               queryFn: () => fetchDebts(userId),                      staleTime: 60_000 },
    ],
  })

  const [accQ, sumQ, catQ, goalQ, debtQ] = results
  const loading = results.some((r) => r.isLoading)

  const accounts = accQ.data || []
  const summary  = sumQ.data || {}
  const cats     = (catQ.data || []).slice(0, 5)
  const goals    = goalQ.data || []
  const debts    = debtQ.data || []

  // Total balance across all accounts in UAH
  const totalUAH = accounts.reduce((sum, acc) => sum + toUAH(acc.balance, acc.currency, rates), 0)

  // 30-day expense chart from transactions (fallback: empty)
  const thirtyDaysAgo = new Date()
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30)

  const chartQuery = useQueries({
    queries: [{
      queryKey: ['txn-chart', userId],
      queryFn: () => fetchTransactions(userId, {
        type: 'expense',
        date_from: thirtyDaysAgo.toISOString(),
        limit: 200,
      }),
      staleTime: 120_000,
    }],
  })
  const chartTxns = chartQuery[0].data || []
  const chartData = buildExpenseChartData(chartTxns)

  // Pie chart
  const pieTotal = cats.reduce((s, c) => s + (c.total_uah || 0), 0)
  const pieData = cats.map((c) => ({ name: c.name || 'Інше', value: Math.round(c.total_uah || 0) }))

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Фінанси</div>
          <div className="page-sub">{month.replace('-', ' / ')}</div>
        </div>
      </div>

      <div className="page-content" style={{ paddingTop: 0 }}>
        {/* Balance hero */}
        <div className="section">
          <div className="card-hero">
            <div className="balance-label">Загальний баланс</div>
            {loading ? (
              <Skeleton h={40} w="70%" style={{ marginBottom: 8 }} />
            ) : (
              <>
                <div className="balance-amount">~{fmtUAH(totalUAH)}</div>
                <div className={`balance-change ${(summary.net_uah || 0) >= 0 ? 'pos' : 'neg'}`}>
                  {(summary.net_uah || 0) >= 0 ? '+' : ''}{fmtUAH(summary.net_uah || 0)} цього місяця
                </div>
              </>
            )}
          </div>
        </div>

        {/* Stats */}
        <div className="section">
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-label">Доходи</div>
              {loading
                ? <Skeleton h={24} w="60%" />
                : <div className="stat-value income">{fmtUAH(summary.total_income_uah || 0)}</div>
              }
            </div>
            <div className="stat-card">
              <div className="stat-label">Витрати</div>
              {loading
                ? <Skeleton h={24} w="60%" />
                : <div className="stat-value expense">{fmtUAH(summary.total_expense_uah || 0)}</div>
              }
            </div>
          </div>
        </div>

        {/* Account cards */}
        <div className="section">
          <div className="section-label">Рахунки</div>
          {loading ? (
            <div style={{ display: 'flex', gap: 10 }}>
              <Skeleton h={100} w={150} />
              <Skeleton h={100} w={150} />
            </div>
          ) : accounts.length === 0 ? (
            <div className="empty-state" style={{ padding: '24px 0' }}>
              <div className="empty-icon">🏦</div>
              <div className="empty-text">Рахунків ще немає</div>
            </div>
          ) : (
            <div className="accounts-scroll">
              {accounts.map((acc) => {
                const uah = toUAH(acc.balance, acc.currency, rates)
                return (
                  <div key={acc.id} className={`acc-card${acc.is_default ? ' default' : ''}`}>
                    <span className="acc-flag">{CURRENCY_FLAGS[acc.currency] || '💱'}</span>
                    <div className="acc-name">{acc.name}</div>
                    <div className="acc-bal">{fmtAmount(acc.balance, acc.currency)}</div>
                    {acc.currency !== 'UAH' && (
                      <div className="acc-curr">~{fmtUAH(uah)}</div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* 30-day expense chart */}
        <div className="section">
          <div className="chart-wrap">
            <div className="chart-title">Витрати за 30 днів</div>
            {chartQuery[0].isLoading ? (
              <Skeleton h={140} />
            ) : (
              <ResponsiveContainer width="100%" height={140}>
                <AreaChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                  <defs>
                    <linearGradient id="expGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#5557f5" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#5557f5" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="day"
                    tick={{ fontSize: 10, fill: '#6b7280' }}
                    tickLine={false}
                    axisLine={false}
                    interval={6}
                  />
                  <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} tickLine={false} axisLine={false} />
                  <Tooltip content={<CustomTooltip />} />
                  <Area
                    type="monotone"
                    dataKey="amount"
                    stroke="#5557f5"
                    strokeWidth={2}
                    fill="url(#expGrad)"
                    dot={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Top-5 categories pie */}
        {cats.length > 0 && (
          <div className="section">
            <div className="chart-wrap">
              <div className="chart-title">Топ категорій витрат</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <PieChart width={120} height={120}>
                  <Pie data={pieData} cx={55} cy={55} innerRadius={34} outerRadius={54} paddingAngle={2} dataKey="value" strokeWidth={0}>
                    {pieData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                  </Pie>
                </PieChart>
                <div style={{ flex: 1 }}>
                  {cats.map((c, i) => (
                    <div key={c.category_id || i} className="cat-row">
                      <div className="cat-dot" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                      <span className="cat-name">{c.icon ? `${c.icon} ` : ''}{c.name || 'Інше'}</span>
                      <span className="cat-val">{fmtUAH(c.total_uah || 0)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Goals */}
        {goals.length > 0 && (
          <div className="section">
            <div className="section-label">Цілі</div>
            <div className="card">
              {goals.map((g) => {
                const pct = Math.min(100, Math.round(g.progress_percent || 0))
                return (
                  <div key={g.id} className="progress-item">
                    <div className="progress-row">
                      <span className="progress-name">🎯 {g.name}</span>
                      <span className="progress-meta">{pct}%</span>
                    </div>
                    <div className="progress-track">
                      <div
                        className={`progress-fill${pct >= 100 ? ' success' : pct >= 70 ? '' : ''}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Debts */}
        {debts.length > 0 && (
          <div className="section">
            <div className="section-label">Борги</div>
            <div className="card">
              {debts.map((d) => {
                const total = d.total_amount || 1
                const remaining = d.remaining_amount || 0
                const paid = total - remaining
                const pct = Math.min(100, Math.round((paid / total) * 100))
                return (
                  <div key={d.id} className="progress-item">
                    <div className="progress-row">
                      <span className="progress-name">💳 {d.name}</span>
                      <span className="progress-meta">{fmtAmount(remaining, d.currency || 'UAH')} залишилось</span>
                    </div>
                    <div className="progress-track">
                      <div
                        className={`progress-fill${pct >= 80 ? ' success' : pct >= 40 ? ' warn' : ' danger'}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
