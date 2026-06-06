import { useQuery } from '@tanstack/react-query'

// 1 UAH = X units of foreign currency  →  1 X = 1/rate UAH
// open.er-api.com returns rates relative to base (UAH here)
const FALLBACK = { USD: 0.0243, EUR: 0.0222, USDT: 0.0243, BTC: 0.00000038, ETH: 0.0000077 }

async function loadRates() {
  try {
    const r = await fetch('https://open.er-api.com/v6/latest/UAH')
    const data = await r.json()
    return { ...FALLBACK, ...data.rates }
  } catch {
    return FALLBACK
  }
}

export function useExchangeRates() {
  return useQuery({
    queryKey: ['exchange-rates'],
    queryFn: loadRates,
    staleTime: 3_600_000,
    retry: false,
    placeholderData: FALLBACK,
  })
}

export function toUAH(amount, currency, rates) {
  if (!currency || currency === 'UAH') return amount
  // USDT treated as USD for simplicity
  const key = currency === 'USDT' ? 'USD' : currency
  const rate = rates?.[key]
  if (!rate || rate === 0) return amount
  return amount / rate
}

export function fmtUAH(amount) {
  return `${Math.round(amount).toLocaleString('uk-UA')} ₴`
}

export function fmtAmount(amount, currency) {
  const rounded = currency === 'UAH' ? Math.round(amount) : +amount.toFixed(2)
  return `${rounded.toLocaleString('uk-UA')} ${currency}`
}
