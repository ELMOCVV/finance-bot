import { useState } from 'react'
import { BottomNav } from './components/BottomNav'
import Dashboard    from './pages/Dashboard'
import Transactions from './pages/Transactions'
import Analytics    from './pages/Analytics'
import Accounts     from './pages/Accounts'
import { useTelegramUser } from './hooks/useTelegramUser'

const PAGES = { dashboard: Dashboard, transactions: Transactions, analytics: Analytics, accounts: Accounts }

export default function App() {
  const [page, setPage] = useState('dashboard')
  const user = useTelegramUser()
  const Page = PAGES[page]

  return (
    <div className="layout">
      <Page userId={user.id} />
      <BottomNav active={page} onChange={setPage} />
    </div>
  )
}
