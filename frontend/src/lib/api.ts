export const BASE_URL = 'http://localhost:8000'
export const WS_BASE = 'ws://localhost:8000/api'

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${await res.text()}`)
  }
  return res.json() as Promise<T>
}

// Types for API responses
export interface Algorithm {
  name: string
  display_name: string
  required_tfs: string[]
  exec_tf: string
  needs_fit: boolean
  description: string
  indicator_keys: string[]
}

export interface Stock {
  symbol: string
  name: string
  tick_size: number
  spread_points: number
  yfinance_ticker: string
  available_tfs: string[]
  last_synced: number | null    // Unix timestamp of most recently modified TF file
  last_data_date: string | null // Latest bar date in the data (YYYY-MM-DD)
}

export interface BacktestMetrics {
  trade_count: number
  win_rate_pct: number
  profit_factor: number
  expectancy_pips: number
  expectancy_R: number
  avg_win_pips: number
  avg_loss_pips: number
  max_dd_pips: number
  max_dd_R: number
  total_profit_pips: number
  total_R: number
  sharpe: number
}

export interface BacktestResult {
  id: string
  algo: string
  symbol: string
  exec_tf: string
  metrics: BacktestMetrics
  trades: Trade[]
  run_at: string
  error: string | null
}

export interface Trade {
  entry_time: string
  exit_time: string | null
  direction: string        // 'buy' | 'sell'
  entry_price: number
  exit_price: number | null
  sl: number               // final SL (may be trailed from initial)
  initial_sl: number       // SL at entry — use this for risk sizing and display
  tp: number
  profit_pips: number | null
  exit_reason: string      // 'sl' | 'trail' | 'tp' | 'time' | 'eod'
}

export interface ReplayBar {
  open: number
  high: number
  low: number
  close: number
}

export interface ReplaySignal {
  direction: string
  entry_price: number
  sl: number
  tp: number
  atr: number
}

export interface ReplayOpenTrade {
  direction: string
  entry_price: number
  sl: number
  tp: number
  open_bars: number
}

export interface ReplayTradeClosed {
  direction: string
  profit_pips: number
  outcome: string
}

export interface ReplayFrame {
  type: 'frame'
  bar_index: number
  bar_time: string
  bar: ReplayBar
  signal: ReplaySignal | null
  open_trade: ReplayOpenTrade | null
  trade_closed: ReplayTradeClosed | null
  indicator_snapshot: Record<string, number | string>
  total_bars: number
}

export interface LogEntry {
  ts: string
  type: string
  [key: string]: unknown
}

export interface StockTFEntry {
  bar_count: number
  file_size_bytes: number
  start_date: string
  end_date: string
  last_modified: number
}

export interface StockTFInfo {
  [tf: string]: StockTFEntry
}

export interface SyncJobEntry {
  symbol: string
  status: 'done' | 'error'
  bars?: Record<string, number>
  error?: string
}

export interface SyncJob {
  status: 'running' | 'complete'
  done: number
  total: number
  progress: SyncJobEntry[]
}

export interface OHLCBar {
  time: number
  open: number
  high: number
  low: number
  close: number
}
