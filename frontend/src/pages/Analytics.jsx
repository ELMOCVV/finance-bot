import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
  PieChart, Pie, Cell,
} from 'recharts'
import { CaretLeft, CaretRight } from '@phosphor-icons/react'
import { fetchAnalyticsSummary, fetchAnalyticsByCategory, fetchAnalyticsTrend } from '../api/queries'
import { fmtUAH } from '../api/rates'
import { currentMonth, prevMonth, nextMonth, fmtMonth } from '../hooks/useTelegramUser'
import { SkeletonCard, Skeleton } from '../components/Skeleton'

const PIE_COLORS = ['#5557f5', '#10b981', '#f59e0b', '#f43f5e', '#8b5cf6', '#06b6d4', '#ec4899']

const BAR_TOOLTIP = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
      <div style={{ color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} style={{ color: p.fill, fontWeight: 700 }}>{fmtUAH(p.value)}</div>
      ))}
    </div>
  )
}

export default function Analytics({ userId }) {
  const [month, setMonth] = useState(currentMonth())
  const isCurrentMonth = month === currentMonth()

  const { data: summary, isLoading: sumLoading } = useQuery({
    queryKey: ['summary', userId, month],
    queryFn: () => fetchAnalyticsSummary(userId, month),
    staleTime: 60_000,
  })
  const { data: cats = [], isLoading: catLoading } = useQuery({
    queryKey: ['by-category', userId, month],
    queryFn: () => fetchAnalyticsByCategory(userId, month),
    staleTime: 60_000,
  })
  const { data: trend = [], isLoading: trendLoading } = useQuery({
    queryKey: ['trend', userId],
    queryFn: () => fetchAnalyticsTrend(userId, 6),
    staleTime: 120_000,
  })

  // Previous month comparison
  const { data: prevSummary } = useQuery({
    queryKey: ['summary', userId, prevMonth(month)],
    queryFn: () => fetchAnalyticsSummary(userId, prevMonth(month)),
    staleTime: 120_000,
  })

  const pieTotal = cats.reduce((s, c) => s + (c.total_uah || 0), 0)
  const pieData  = cats.slice(0, 7).map((c) => ({ name: c.name || 'Інше', value: Math.round(c.total_uah || 0) }))

  const trendFormatted = trend.map((t) => ({
    month: (t.month || '').slice(5),
    Доходи:  Math.round(t.total_income  || t.income  || 0),
    Витрати: Math.round(t.total_expense || t.expense || 0),
  }))

  const expenseDelta = prevSummary
    ? ((summary?.total_expense_uah || 0) - (prevSummary?.total_expense_uah || 0))
    : null

  return (
    <div>
      <div className="page-header">
        <div className="page-title">Аналітика</div>
      </div>

      {/* Month selector */}
      <div className="month-nav">
        <button className="month-nav-btn" onClick={() => setMonth(prevMonth(month))}>
          <CaretLeft size={16} weight="bold" />
        </button>
        <span className="month-nav-label">{fmtMonth(month)}</span>
        <button
          className="month-nav-btn"
          onClick={() => !isCurrentMonth && setMonth(nextMonth(month))}
          style={{ opacity: isCurrentMonth ? 0.3 : 1, pointerEvents: isCurrentMonth ? 'none' : 'auto' }}
        >
          <CaretRight size={16} weight="bold" />
        </button>
      </div>

      <div className="page-content" style={{ paddingTop: 0 }}>
        {/* Summary stats */}
        {sumLoading ? (
          <div className="stats-grid" style={{ marginBottom: 20 }}>
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : (
          <>
            <div className="stats-grid" style={{ marginBottom: 10 }}>
              <div className="stat-card">
                <div className="stat-label">Доходи</div>
                <div className="stat-value income">{fmtUAH(summary?.total_income_uah || 0)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Витрати</div>
                <div className="stat-value expense">{fmtUAH(summary?.total_expense_uah || 0)}</div>
              </div>
            </div>
            <div className="stat-card" style={{ marginBottom: 20 }}>
              <div className="stat-label">Чистий результат</div>
              <div className={`stat-value ${(summary?.net_uah || 0) >= 0 ? 'income' : 'expense'}`}>
                {(summary?.net_uah || 0) >= 0 ? '+' : ''}{fmtUAH(summary?.net_uah || 0)}
              </div>
            </div>
          </>
        )}

        {/* Comparison strip */}
        {expenseDelta !== null && (
          <div className="compare-strip">
            <div className="compare-card">
              <div className="compare-label">Минулий місяць</div>
              <div className="compare-val">{fmtUAH(prevSummary?.total_expense_uah || 0)}</div>
            </div>
            <div className="compare-card">
              <div className="compare-label">Різниця</div>
              <div
                className="compare-val"
                style={{ color: expenseDelta > 0 ? 'var(--danger)' : 'var(--success)' }}
              >
                {expenseDelta > 0 ? '+' : ''}{fmtUAH(expenseDelta)}
              </div>
            </div>
          </div>
        )}

        {/* Monthly trend */}
        {!trendLoading && trendFormatted.length > 0 && (
          <div className="section">
            <div className="chart-wrap">
              <div className="chart-title">Доходи / Витрати по місяцях</div>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={trendFormatted} margin={{ top: 4, right: 4, bottom: 0, left: -20 }} barCategoryGap="30%">
                  <XAxis dataKey="month" tick={{ fontSize: 10, fill: '#6b7280' }} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} tickLine={false} axisLine={false} />
                  <Tooltip content={<BAR_TOOLTIP />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                  <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
                  <Bar dataKey="Доходи"  fill="#10b981" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="Витрати" fill="#f43f5e" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Categories breakdown */}
        {!catLoading && cats.length > 0 && (
          <div className="section">
            <div className="chart-wrap">
              <div className="chart-title">Розбивка по категоріях</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                <PieChart width={110} height={110}>
                  <Pie data={pieData} cx={50} cy={50} innerRadius={28} outerRadius={50} paddingAngle={2} dataKey="value" strokeWidth={0}>
                    {pieData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                  </Pie>
                </PieChart>
                <div style={{ flex: 1 }}>
                  {cats.slice(0, 7).map((c, i) => {
                    const pct = pieTotal > 0 ? Math.round((c.total_uah / pieTotal) * 100) : 0
                    return (
                      <div key={c.category_id || i} className="cat-row">
                        <div className="cat-dot" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                        <span className="cat-name">{c.icon ? `${c.icon} ` : ''}{c.name || 'Інше'}</span>
                        <span className="cat-pct">{pct}%</span>
                        <span className="cat-val">{fmtUAH(c.total_uah || 0)}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          </div>
        )}

        {!catLoading && cats.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon">📊</div>
            <div className="empty-text">Немає даних за цей місяць</div>
          </div>
        )}
      </div>
    </div>
  )
}
