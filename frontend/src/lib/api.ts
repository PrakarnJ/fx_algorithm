// Relative in dev (proxied by Vite, see vite.config.ts) and in prod (FastAPI serves the SPA on the same origin).
export const BASE_URL = ''

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
  last_synced: string | null
  timeframes: Record<string, {
    bars: number
    start: string | null
    end: string | null
    last_modified: string
  }>
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

export interface ExitLevels {
  stop: (number | null)[]
  limit: (number | null)[]
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
  exit_levels: ExitLevels | null
  metrics: TesterMetrics | null
}

export interface TesterSettingsOverride {
  initial_capital?: number
  default_qty_type?: string
  default_qty_value?: number
  commission_type?: string
  commission_value?: number
}

export interface PineBacktestRequest {
  source: string
  timeframe: string
  start_date?: string | null
  end_date?: string | null
  settings?: TesterSettingsOverride | null
}

export function runPineBacktest(req: PineBacktestRequest): Promise<PineBacktestResponse> {
  return apiFetch<PineBacktestResponse>('/api/pine/backtest', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

// ── saved scripts ─────────────────────────────────────────────────────────────

export interface ScriptMeta {
  id: number
  name: string
  created_at: string
  updated_at: string
}

export interface ScriptDetail extends ScriptMeta {
  source: string
}

export function listScripts(): Promise<{ scripts: ScriptMeta[] }> {
  return apiFetch('/api/scripts')
}

export function getScript(id: number): Promise<ScriptDetail> {
  return apiFetch(`/api/scripts/${id}`)
}

export function createScript(name: string, source: string): Promise<ScriptDetail> {
  return apiFetch('/api/scripts', { method: 'POST', body: JSON.stringify({ name, source }) })
}

export function updateScript(
  id: number,
  patch: { name?: string; source?: string },
): Promise<ScriptDetail> {
  return apiFetch(`/api/scripts/${id}`, { method: 'PUT', body: JSON.stringify(patch) })
}

export function deleteScript(id: number): Promise<{ ok: boolean }> {
  return apiFetch(`/api/scripts/${id}`, { method: 'DELETE' })
}

// ── ranking ───────────────────────────────────────────────────────────────────

export interface RankingRequest {
  script_ids: number[]
  timeframe: string
  start_date?: string | null
  end_date?: string | null
}

export interface RankingItem {
  script_id: number
  name: string
  ok: boolean
  title: string | null
  error: string | null
  metrics: TesterMetrics | null
}

export interface RankingResponse {
  ok: boolean
  timeframe: string
  bars: number
  start: string | null
  end: string | null
  results: RankingItem[]
}

export function runRanking(req: RankingRequest): Promise<RankingResponse> {
  return apiFetch('/api/ranking/run', { method: 'POST', body: JSON.stringify(req) })
}

// ── data sync ─────────────────────────────────────────────────────────────────

export interface SyncStatus {
  status: 'idle' | 'running' | 'done' | 'error'
  mode: 'full' | 'incremental' | null
  step: string | null
  started_at: string | null
  finished_at: string | null
  error: string | null
  last_synced: string | null
}

export function startDataSync(mode: 'auto' | 'full' = 'auto'): Promise<{ status: string; mode: string }> {
  return apiFetch('/api/data/sync', { method: 'POST', body: JSON.stringify({ mode }) })
}

// ── logs ──────────────────────────────────────────────────────────────────────

export interface LogEntry {
  ts: string
  type: string
  [key: string]: unknown
}
