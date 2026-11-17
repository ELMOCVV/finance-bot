import { House, List, ChartBar, Bank } from '@phosphor-icons/react'

const TABS = [
  { id: 'dashboard',    label: 'Главная',   Icon: House },
  { id: 'transactions', label: 'Транзакции', Icon: List },
  { id: 'analytics',   label: 'Аналитика', Icon: ChartBar },
  { id: 'accounts',    label: 'Счета',   Icon: Bank },
]

export function BottomNav({ active, onChange }) {
  return (
    <nav className="bottom-nav">
      {TABS.map(({ id, label, Icon }) => (
        <button
          key={id}
          className={`nav-item${active === id ? ' active' : ''}`}
          onClick={() => onChange(id)}
        >
          <Icon size={22} weight={active === id ? 'fill' : 'regular'} />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  )
}
