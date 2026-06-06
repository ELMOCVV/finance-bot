import { House, List, ChartBar, Bank } from '@phosphor-icons/react'

const TABS = [
  { id: 'dashboard',    label: 'Головна',   Icon: House },
  { id: 'transactions', label: 'Транзакції', Icon: List },
  { id: 'analytics',   label: 'Аналітика', Icon: ChartBar },
  { id: 'accounts',    label: 'Рахунки',   Icon: Bank },
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
