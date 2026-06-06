import { api } from './client'

const p = (userId, extra = {}) => ({ user_id: userId, ...extra })

export const fetchAccounts = (userId) =>
  api.get('/accounts/', { params: p(userId) }).then((r) => r.data)

export const fetchTransactions = (userId, extra = {}) =>
  api.get('/transactions/', { params: p(userId, { limit: 100, ...extra }) }).then((r) => r.data)

export const fetchAnalyticsSummary = (userId, month) =>
  api.get('/analytics/summary', { params: p(userId, { month }) }).then((r) => r.data)

export const fetchAnalyticsByCategory = (userId, month) =>
  api.get('/analytics/by-category', { params: p(userId, { month }) }).then((r) => r.data)

export const fetchAnalyticsTrend = (userId, months = 6) =>
  api.get('/analytics/trend', { params: p(userId, { months }) }).then((r) => r.data)

export const fetchGoals = (userId) =>
  api.get('/goals/', { params: p(userId) }).then((r) => r.data)

export const fetchDebts = (userId) =>
  api.get('/debts/', { params: p(userId) }).then((r) => r.data)

export const createAccount = (userId, data) =>
  api.post('/accounts/', data, { params: p(userId) }).then((r) => r.data)
