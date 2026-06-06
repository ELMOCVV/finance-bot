import { useMemo } from 'react'

export function useTelegramUser() {
  return useMemo(() => {
    try {
      const tg = window.Telegram?.WebApp
      if (tg) {
        tg.ready()
        tg.expand()
        const user = tg.initDataUnsafe?.user
        if (user?.id) {
          return { id: user.id, name: user.first_name || 'User' }
        }
      }
    } catch {}
    return { id: 1, name: 'Demo' }
  }, [])
}

export function currentMonth() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

export function prevMonth(month) {
  const [y, m] = month.split('-').map(Number)
  const d = new Date(y, m - 2, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

export function nextMonth(month) {
  const [y, m] = month.split('-').map(Number)
  const d = new Date(y, m, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

export function fmtMonth(month) {
  const [y, m] = month.split('-').map(Number)
  const MONTHS = ['Січень','Лютий','Березень','Квітень','Травень','Червень',
                  'Липень','Серпень','Вересень','Жовтень','Листопад','Грудень']
  return `${MONTHS[m - 1]} ${y}`
}
