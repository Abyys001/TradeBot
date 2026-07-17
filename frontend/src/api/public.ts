import axios from 'axios'

// Unauthenticated, no-CSRF client for the public marketing site — these
// endpoints run with authentication_classes=[] on the backend (see
// apps/public/views.py), so unlike api/client.ts there's no session/CSRF
// dance to do here.
const publicApi = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

export interface PublicPerformanceHeadline {
  net_realized_pnl: string
  win_rate: number
  total_closed_trades: number
  active_strategies: number
  active_investors_band: string
}

export interface PublicEquityPoint {
  date: string
  equity: number
}

export interface PublicPerformance {
  as_of: string
  since_days: number
  headline: PublicPerformanceHeadline
  equity_curve: PublicEquityPoint[]
  disclaimer: string
}

export async function getPublicPerformance(): Promise<PublicPerformance> {
  const { data } = await publicApi.get<PublicPerformance>('/public/performance/')
  return data
}

export interface LeadPayload {
  name: string
  email: string
  contact?: string
  message?: string
  locale?: string
  website?: string // honeypot — must stay empty
}

export async function submitLead(payload: LeadPayload): Promise<void> {
  await publicApi.post('/public/leads/', payload)
}
