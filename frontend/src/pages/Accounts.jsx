import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus } from '@phosphor-icons/react'
import { fetchAccounts, createAccount } from '../api/queries'
import { useExchangeRates, toUAH, fmtUAH, fmtAmount } from '../api/rates'
import { SkeletonList } from '../components/Skeleton'

const CURRENCY_FLAGS = { UAH: '🇺🇦', USD: '🇺🇸', USDT: '💵', EUR: '🇪🇺', BTC: '₿', ETH: 'Ξ' }
const CURRENCIES = ['UAH', 'USD', 'EUR', 'USDT', 'BTC', 'ETH']

const DEFAULTS = { name: '', currency: 'UAH', balance: '', is_default: false }

export default function Accounts({ userId }) {
  const [showModal, setShowModal] = useState(false)
  const [form, setForm] = useState(DEFAULTS)
  const [err, setErr] = useState('')

  const qc = useQueryClient()
  const { data: rates } = useExchangeRates()

  const { data: accounts = [], isLoading, isError } = useQuery({
    queryKey: ['accounts', userId],
    queryFn: () => fetchAccounts(userId),
    staleTime: 60_000,
  })

  const totalUAH = accounts.reduce((s, acc) => s + toUAH(acc.balance, acc.currency, rates), 0)

  const { mutate: addAccount, isPending } = useMutation({
    mutationFn: () =>
      createAccount(userId, {
        name: form.name.trim(),
        currency: form.currency,
        is_default: form.is_default,
        balance: parseFloat(form.balance) || 0,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['accounts', userId] })
      setShowModal(false)
      setForm(DEFAULTS)
      setErr('')
    },
    onError: (e) => setErr(e?.response?.data?.detail || 'Помилка створення рахунку'),
  })

  function handleSubmit(e) {
    e.preventDefault()
    setErr('')
    if (!form.name.trim()) return setErr('Введіть назву рахунку')
    addAccount()
  }

  return (
    <div>
      <div className="page-header">
        <div className="page-title">Рахунки</div>
      </div>

      <div className="page-content" style={{ paddingTop: 0 }}>
        {/* Total */}
        {accounts.length > 0 && (
          <div className="card-hero" style={{ marginBottom: 20 }}>
            <div className="balance-label">Загальний баланс</div>
            <div className="balance-amount">~{fmtUAH(totalUAH)}</div>
            <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 6 }}>
              {accounts.length} {accounts.length === 1 ? 'рахунок' : accounts.length < 5 ? 'рахунки' : 'рахунків'}
            </div>
          </div>
        )}

        {/* List */}
        {isLoading ? (
          <SkeletonList rows={3} />
        ) : isError ? (
          <div className="error-msg">Помилка завантаження рахунків</div>
        ) : accounts.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">🏦</div>
            <div className="empty-text">Рахунків ще немає.<br />Додайте перший!</div>
          </div>
        ) : (
          accounts.map((acc) => {
            const approxUAH = acc.currency !== 'UAH' ? toUAH(acc.balance, acc.currency, rates) : null
            return (
              <div key={acc.id} className="acc-manage">
                <div className="acc-manage-flag">{CURRENCY_FLAGS[acc.currency] || '💱'}</div>
                <div className="acc-manage-body">
                  <div className="acc-manage-name">{acc.name}</div>
                  <div className="acc-manage-bal">
                    {fmtAmount(acc.balance, acc.currency)}
                    {approxUAH !== null && ` · ~${fmtUAH(approxUAH)}`}
                  </div>
                </div>
                {acc.is_default && <div className="acc-manage-badge">Основний</div>}
              </div>
            )
          })
        )}
      </div>

      {/* FAB */}
      <button className="fab" onClick={() => setShowModal(true)}>
        <Plus size={24} weight="bold" />
      </button>

      {/* Add account modal */}
      {showModal && (
        <div className="overlay" onClick={(e) => e.target === e.currentTarget && setShowModal(false)}>
          <form className="sheet" onSubmit={handleSubmit}>
            <div className="sheet-title">Новий рахунок</div>

            <div className="form-field">
              <label className="form-label">Назва</label>
              <input
                className="form-input"
                type="text"
                placeholder="Моно, Приват, Готівка..."
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                autoFocus
                maxLength={64}
              />
            </div>

            <div className="form-field">
              <label className="form-label">Валюта</label>
              <div className="currency-grid">
                {CURRENCIES.map((c) => (
                  <button
                    key={c}
                    type="button"
                    className={`currency-pill${form.currency === c ? ' selected' : ''}`}
                    onClick={() => setForm({ ...form, currency: c })}
                  >
                    {CURRENCY_FLAGS[c] || '💱'} {c}
                  </button>
                ))}
              </div>
            </div>

            <div className="form-field">
              <label className="form-label">Початковий баланс</label>
              <input
                className="form-input"
                type="number"
                placeholder="0"
                value={form.balance}
                onChange={(e) => setForm({ ...form, balance: e.target.value })}
                min="0"
                step="0.01"
              />
            </div>

            <div className="form-field">
              <div className="form-checkbox-row">
                <input
                  type="checkbox"
                  id="isDefault"
                  checked={form.is_default}
                  onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
                />
                <label htmlFor="isDefault" style={{ cursor: 'pointer' }}>Зробити основним</label>
              </div>
            </div>

            {err && <div className="error-msg" style={{ padding: '8px 0' }}>{err}</div>}

            <div className="sheet-actions">
              <button
                type="button"
                className="btn secondary full"
                onClick={() => { setShowModal(false); setErr('') }}
              >
                Скасувати
              </button>
              <button type="submit" className="btn primary full" disabled={isPending}>
                {isPending ? 'Збереження...' : 'Додати'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}
