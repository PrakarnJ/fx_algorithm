import { useState, useMemo } from 'react'
import { ArrowUpDown, ArrowUp, ArrowDown, Play, List } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { MetricBadge } from './MetricBadge'
import { formatPips, formatR, formatDateTime } from '@/lib/formatters'
import type { BacktestResult } from '@/lib/api'
import { cn } from '@/lib/utils'

type SortKey = 'rank' | 'algo' | 'symbol' | 'trade_count' | 'win_rate_pct' | 'profit_factor' | 'expectancy_pips' | 'expectancy_R' | 'max_dd_pips' | 'sharpe' | 'run_at'
type SortDir = 'asc' | 'desc'

interface Column {
  key: SortKey
  label: string
  align?: 'right' | 'left'
}

const COLUMNS: Column[] = [
  { key: 'rank', label: '#' },
  { key: 'algo', label: 'Algorithm' },
  { key: 'symbol', label: 'Symbol' },
  { key: 'trade_count', label: 'Trades', align: 'right' },
  { key: 'win_rate_pct', label: 'Win%', align: 'right' },
  { key: 'profit_factor', label: 'PF', align: 'right' },
  { key: 'expectancy_pips', label: 'Exp(pips)', align: 'right' },
  { key: 'expectancy_R', label: 'Exp(R)', align: 'right' },
  { key: 'max_dd_pips', label: 'Max DD(pips)', align: 'right' },
  { key: 'sharpe', label: 'Sharpe', align: 'right' },
  { key: 'run_at', label: 'Run At' },
]

function getValue(result: BacktestResult, key: SortKey): number | string {
  switch (key) {
    case 'rank': return 0
    case 'algo': return result.algo
    case 'symbol': return result.symbol
    case 'run_at': return result.run_at
    case 'trade_count': return result.metrics?.trade_count ?? 0
    case 'win_rate_pct': return result.metrics?.win_rate_pct ?? 0
    case 'profit_factor': return result.metrics?.profit_factor ?? 0
    case 'expectancy_pips': return result.metrics?.expectancy_pips ?? 0
    case 'expectancy_R': return result.metrics?.expectancy_R ?? 0
    case 'max_dd_pips': return result.metrics?.max_dd_pips ?? 0
    case 'sharpe': return result.metrics?.sharpe ?? 0
    default: return 0
  }
}

interface RankingTableProps {
  results: BacktestResult[]
  onReplay?: (algo: string, symbol: string) => void
  onShowTrades?: (result: BacktestResult) => void
}

export function RankingTable({ results, onReplay, onShowTrades }: RankingTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('profit_factor')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  function handleSort(key: SortKey) {
    if (key === 'rank') return
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  const sorted = useMemo(() => {
    const valid = results.filter(r => !r.error && r.metrics)
    return [...valid].sort((a, b) => {
      const av = getValue(a, sortKey)
      const bv = getValue(b, sortKey)
      const cmp = typeof av === 'string' && typeof bv === 'string'
        ? av.localeCompare(bv)
        : (av as number) - (bv as number)
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [results, sortKey, sortDir])

  function SortIcon({ col }: { col: SortKey }) {
    if (col === 'rank') return null
    if (sortKey !== col) return <ArrowUpDown className="ml-1 h-3 w-3 opacity-40 inline" />
    return sortDir === 'asc'
      ? <ArrowUp className="ml-1 h-3 w-3 text-accent inline" />
      : <ArrowDown className="ml-1 h-3 w-3 text-accent inline" />
  }

  if (sorted.length === 0) {
    return (
      <div className="text-center py-16 text-muted-foreground font-mono text-sm">
        <div className="text-2xl mb-2 text-accent">_</div>
        No backtest results yet. Run a backtest to see rankings.
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-card-border">
            {COLUMNS.map(col => (
              <th
                key={col.key}
                onClick={() => handleSort(col.key)}
                className={cn(
                  'px-3 py-3 font-mono text-xs text-muted-foreground uppercase tracking-wider select-none',
                  col.key !== 'rank' && 'cursor-pointer hover:text-foreground',
                  col.align === 'right' ? 'text-right' : 'text-left',
                )}
              >
                {col.label}
                <SortIcon col={col.key} />
              </th>
            ))}
            <th className="px-3 py-3 font-mono text-xs text-muted-foreground uppercase tracking-wider text-right">
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((result, idx) => (
            <tr
              key={result.id}
              className="border-b border-card-border/50 hover:bg-secondary/20 transition-colors"
            >
              <td className="px-3 py-3 font-mono text-muted-foreground text-xs">
                {idx + 1}
              </td>
              <td className="px-3 py-3 font-mono text-foreground font-medium">
                {result.algo}
              </td>
              <td className="px-3 py-3 font-mono text-accent">
                {result.symbol}
              </td>
              <td className="px-3 py-3 text-right font-mono text-foreground">
                {result.metrics?.trade_count ?? '—'}
              </td>
              <td className="px-3 py-3 text-right">
                <MetricBadge value={result.metrics?.win_rate_pct ?? 0} type="wr" />
              </td>
              <td className="px-3 py-3 text-right">
                <MetricBadge value={result.metrics?.profit_factor ?? 0} type="pf" />
              </td>
              <td className="px-3 py-3 text-right font-mono text-foreground">
                {formatPips(result.metrics?.expectancy_pips)}
              </td>
              <td className="px-3 py-3 text-right font-mono text-foreground">
                {formatR(result.metrics?.expectancy_R)}
              </td>
              <td className="px-3 py-3 text-right">
                <MetricBadge value={result.metrics?.max_dd_pips ?? 0} type="dd" />
              </td>
              <td className="px-3 py-3 text-right">
                <MetricBadge value={result.metrics?.sharpe ?? 0} type="sharpe" />
              </td>
              <td className="px-3 py-3 font-mono text-xs text-muted-foreground whitespace-nowrap">
                {formatDateTime(result.run_at)}
              </td>
              <td className="px-3 py-3 text-right">
                <div className="flex items-center justify-end gap-1.5">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 px-2 text-xs"
                    onClick={() => onReplay?.(result.algo, result.symbol)}
                  >
                    <Play className="h-3 w-3 mr-1" />
                    Replay
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 px-2 text-xs"
                    onClick={() => onShowTrades?.(result)}
                  >
                    <List className="h-3 w-3 mr-1" />
                    Trades
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
