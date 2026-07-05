export const BASE_URL = 'http://localhost:8000'

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

// ── chart data ────────────────────────────────────────────────────────────────

export interface OHLCBar {
  time: number
  open: number
  high: number
  low: number
  close: number
}

export interface ChartInfo {
  symbol: string
  timeframes: Record<string, { bars: number; start: string | null; end: string | null }>
}

// ── Pine backtest ─────────────────────────────────────────────────────────────

export interface PineError {
  line: number
  col: number
  message: string
}

export interface PlotSeries {
  id: string
  title: string
  color: string
  style: 'line' | 'histogram' | 'circles'
  overlay: boolean
  values: (number | null)[]
}

export interface ShapeMarker {
  time: number
  shape: string
  location: 'abovebar' | 'belowbar' | 'absolute'
  color: string
  text: string
  price: number | null
}

export interface HLine {
  price: number
  title: string
  color: string
}

export interface TradeRecord {
  entry_time: number
  exit_time: number | null
  direction: 'long' | 'short'
  entry_price: number
  exit_price: number | null
  qty: number
  profit: number | null
  profit_pct: number | null
  entry_id: string
  exit_reason: string
}

export interface TesterMetrics {
  net_profit: number
  net_profit_pct: number
  gross_profit: number
  gross_loss: number
  profit_factor: number | null
  max_drawdown: number
  max_drawdown_pct: number
  total_trades: number
  percent_profitable: number | null
  avg_trade: number | null
  avg_win: number | null
  avg_loss: number | null
  open_pl: number
}

export interface PineBacktestResponse {
  ok: boolean
  script_type: 'indicator' | 'strategy' | null
  title: string | null
  errors: PineError[]
  bars: OHLCBar[]
  plots: PlotSeries[]
  shapes: ShapeMarker[]
  hlines: HLine[]
  trades: TradeRecord[]
  equity: (number | null)[]
  metrics: TesterMetrics | null
}

export interface PineBacktestRequest {
  source: string
  timeframe: string
  start_date?: string | null
  end_date?: string | null
}

export function runPineBacktest(req: PineBacktestRequest): Promise<PineBacktestResponse> {
  return apiFetch<PineBacktestResponse>('/api/pine/backtest', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

// ── logs ──────────────────────────────────────────────────────────────────────

export interface LogEntry {
  ts: string
  type: string
  [key: string]: unknown
}
