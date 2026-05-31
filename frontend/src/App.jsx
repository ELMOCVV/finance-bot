import React, { useState } from 'react'
import { theme } from './styles/theme'
import Dashboard from './pages/Dashboard'
import Transactions from './pages/Transactions'
import Accounts from './pages/Accounts'
import Debts from './pages/Debts'
import Goals from './pages/Goals'

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', icon: '📊' },
  { id: 'transactions', label: 'Транзакції', icon: '💸' },
  { id: 'accounts', label: 'Рахунки', icon: '🏦' },
  { id: 'debts', label: 'Борги', icon: '💳' },
  { id: 'goals', label: 'Цілі', icon: '🎯' },
]

const PAGE_MAP = {
  dashboard: Dashboard,
  transactions: Transactions,
  accounts: Accounts,
  debts: Debts,
  goals: Goals,
}

// Тимчасово хардкодимо user_id=1 для демо; в продакшні — з Telegram WebApp
const USER_ID = 1

export default function App() {
  const [activePage, setActivePage] = useState('dashboard')
  const PageComponent = PAGE_MAP[activePage]

  return (
    <div style={styles.layout}>
      {/* Sidebar */}
      <aside style={styles.sidebar}>
        <div style={styles.logo}>
          <span style={styles.logoIcon}>💰</span>
          <span style={styles.logoText}>FinanceAI</span>
        </div>
        <nav style={styles.nav}>
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              onClick={() => setActivePage(item.id)}
              style={{
                ...styles.navItem,
                ...(activePage === item.id ? styles.navItemActive : {}),
              }}
            >
              <span style={styles.navIcon}>{item.icon}</span>
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
      </aside>

      {/* Main content */}
      <main style={styles.main}>
        <PageComponent userId={USER_ID} />
      </main>
    </div>
  )
}

const styles = {
  layout: {
    display: 'flex',
    minHeight: '100vh',
    backgroundColor: theme.colors.background,
  },
  sidebar: {
    width: '240px',
    backgroundColor: theme.colors.surface,
    borderRight: `1px solid ${theme.colors.border}`,
    display: 'flex',
    flexDirection: 'column',
    padding: '24px 16px',
    gap: '8px',
    flexShrink: 0,
  },
  logo: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '8px 12px 24px',
    borderBottom: `1px solid ${theme.colors.border}`,
    marginBottom: '8px',
  },
  logoIcon: {
    fontSize: '24px',
  },
  logoText: {
    fontSize: theme.fontSizes.xl,
    fontWeight: '700',
    color: theme.colors.text,
    letterSpacing: '-0.5px',
  },
  nav: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  navItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '10px 14px',
    borderRadius: theme.radii.md,
    border: 'none',
    background: 'transparent',
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.sm,
    fontFamily: theme.fonts.base,
    cursor: 'pointer',
    transition: theme.transitions.fast,
    textAlign: 'left',
    width: '100%',
  },
  navItemActive: {
    backgroundColor: theme.colors.accentLight,
    color: theme.colors.accent,
    fontWeight: '600',
  },
  navIcon: {
    fontSize: '18px',
  },
  main: {
    flex: 1,
    padding: '32px',
    overflowY: 'auto',
  },
}
