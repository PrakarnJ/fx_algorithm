import { useMemo, useState } from 'react'
import { LoaderCircle, Play } from 'lucide-react'
import { Checkbox } from '@/components/ui/checkbox'
import { useScripts } from '@/hooks/useApi'
import { runRanking, type RankingItem, type RankingResponse } from '@/lib/api'
import { fmtUsd } from '@/lib/formatters'
import { cn } from '@/lib/utils'

const TIMEFRAMES = ['M15', 'H1', 'H4']

type SortKey = 'net_profit' | 'net_profit_pct' | 'profit_factor' | 'max_drawdown_pct'
  | 'total_trades' | 'percent_profitable' | 'avg_trade'

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: 'net_profit', label: 'Net Profit' },
  { key: 'net_profit_pct', label: 'Net Profit %' },
  { key: 'profit_factor', label: 'Profit Factor' },
  { key: 'max_drawdown_pct', label: 'Max DD %' },
  { key: 'total_trades', label: 'Trades' },
  { key: 'percent_profitable', label: '% Profitable' },
  { key: 'avg_trade', label: 'Avg Trade' },
]

function metricValue(item: RankingItem, key: SortKey): number | null {
  if (!item.ok || !item.metrics) return null
  return item.metrics[key]
}

export function RankingPage() {
  const { data: scriptList } = useScripts()
  const scripts = scriptList?.scripts ?? []

  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [timeframe, setTimeframe] = useState('M15')
  const [startDate, setStartDate] = useState('2025-01-01')
  const [endDate, setEndDate] = useState('')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<RankingResponse | null>(null)
  const [sort, setSort] = useState<{ key: SortKey; dir: 'asc' | 'desc' }>({
    key: 'net_profit', dir: 'desc',
  })

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const run = async () => {
    setRunning(true)
    setError(null)
    try {
      const res = await runRanking({
        script_ids: [...selected],
        timeframe,
        start_date: startDate || null,
        end_date: endDate || null,
      })
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(false)
    }
  }

  const sorted = useMemo(() => {
    if (!result) return []
    const rows = [...result.results]
    rows.sort((a, b) => {
      const va = metricValue(a, sort.key)
      const vb = metricValue(b, sort.key)
      if (va === null && vb === null) return 0
      if (va === null) return 1   // failed / null rows last
      if (vb === null) return -1
      return sort.dir === 'desc' ? vb - va : va - vb
    })
    return rows
  }, [result, sort])

  const clickHeader = (key: SortKey) => {
    setSort((prev) => prev.key === key
      ? { key, dir: prev.dir === 'desc' ? 'asc' : 'desc' }
      : { key, dir: 'desc' })
  }

  const wideM15 = timeframe === 'M15' && !startDate

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Ranking</h1>
        <p className="text-sm text-muted-foreground font-mono mt-1">
          Compare saved scripts over the same bars — fresh backtests each run
        </p>
      </div>

      {/* Controls */}
      <div className="border border-card-border rounded-lg p-4 space-y-4">
        {scripts.length === 0 ? (
          <div className="text-sm text-muted-foreground">
            No saved scripts yet — save scripts in the Studio first.
          </div>
        ) : (
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            {scripts.map((s) => (
              <label key={s.id} className="flex items-center gap-2 text-sm font-mono cursor-pointer">
                <Checkbox
                  checked={selected.has(s.id)}
                  onCheckedChange={() => toggle(s.id)}
                />
                {s.name}
              </label>
            ))}
          </div>
        )}

        <div className="flex items-center gap-3">
          <div className="flex rounded-md border border-card-border overflow-hidden">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={cn(
                  'px-3 py-1 text-xs font-mono transition-colors',
                  timeframe === tf
                    ? 'bg-accent/15 text-accent'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {tf}
              </button>
            ))}
          </div>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="bg-secondary border border-card-border rounded px-2 py-1 text-xs font-mono"
          />
          <span className="text-muted-foreground text-xs">→</span>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="bg-secondary border border-card-border rounded px-2 py-1 text-xs font-mono"
          />
          <button
            onClick={() => void run()}
            disabled={running || selected.size === 0}
            className="flex items-center gap-2 bg-accent/15 text-accent border border-accent/30
                       rounded-md px-4 py-1.5 text-sm font-semibold hover:bg-accent/25
                       disabled:opacity-50 transition-colors"
          >
            {running
              ? <LoaderCircle className="h-4 w-4 animate-spin" />
              : <Play className="h-4 w-4" />}
            {running ? 'Running…' : `Rank ${selected.size || ''}`}
          </button>
          {wideM15 && (
            <span className="text-xs text-muted-foreground">
              M15 full history ≈ 150k bars per script — expect ~10s+ each
            </span>
          )}
        </div>
      </div>

      {error && (
        <div className="px-3 py-2 text-xs font-mono text-red-400 bg-red-950/40 border border-red-900/50 rounded whitespace-pre-wrap">
          {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="border border-card-border rounded-lg overflow-hidden">
          <div className="px-4 py-2 text-xs text-muted-foreground font-mono border-b border-card-border">
            {result.timeframe} · {result.bars.toLocaleString()} bars · {result.start} → {result.end}
            <span className="text-muted-foreground/60"> · approximates TradingView, not tick-identical</span>
          </div>
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="text-muted-foreground border-b border-card-border">
                <th className="text-left px-4 py-2">#</th>
                <th className="text-left px-4 py-2">Name</th>
                {COLUMNS.map((c) => (
                  <th
                    key={c.key}
                    onClick={() => clickHeader(c.key)}
                    className={cn(
                      'text-right px-4 py-2 cursor-pointer select-none hover:text-foreground',
                      sort.key === c.key && 'text-accent',
                    )}
                  >
                    {c.label}{sort.key === c.key ? (sort.dir === 'desc' ? ' ↓' : ' ↑') : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((r, i) => (
                <tr key={r.script_id} className="border-b border-card-border/50 hover:bg-secondary/40">
                  <td className="px-4 py-2 text-muted-foreground">{i + 1}</td>
                  <td className="px-4 py-2">{r.name}</td>
                  {r.ok && r.metrics ? (
                    <>
                      <td className={cn('px-4 py-2 text-right font-semibold',
                        r.metrics.net_profit > 0 ? 'text-emerald-400' : r.metrics.net_profit < 0 ? 'text-red-400' : '')}>
                        {fmtUsd(r.metrics.net_profit)}
                      </td>
                      <td className={cn('px-4 py-2 text-right',
                        r.metrics.net_profit_pct > 0 ? 'text-emerald-400' : r.metrics.net_profit_pct < 0 ? 'text-red-400' : '')}>
                        {r.metrics.net_profit_pct.toFixed(2)}%
                      </td>
                      <td className="px-4 py-2 text-right">
                        {r.metrics.profit_factor !== null ? r.metrics.profit_factor.toFixed(3) : '∞'}
                      </td>
                      <td className="px-4 py-2 text-right text-red-400">
                        {r.metrics.max_drawdown_pct.toFixed(2)}%
                      </td>
                      <td className="px-4 py-2 text-right">{r.metrics.total_trades}</td>
                      <td className="px-4 py-2 text-right">
                        {r.metrics.percent_profitable !== null
                          ? `${r.metrics.percent_profitable.toFixed(2)}%` : '—'}
                      </td>
                      <td className="px-4 py-2 text-right">{fmtUsd(r.metrics.avg_trade)}</td>
                    </>
                  ) : (
                    <td colSpan={COLUMNS.length} className="px-4 py-2 text-red-400">
                      {r.error}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
