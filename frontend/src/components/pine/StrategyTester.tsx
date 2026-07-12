import { useEffect, useRef, useState } from 'react'
import { createChart, type IChartApi, type Time } from 'lightweight-charts'
import type { PineBacktestResponse, TesterMetrics, TradeRecord } from '@/lib/api'
import { fmtLots, fmtUsd } from '@/lib/formatters'
import { cn } from '@/lib/utils'

function fmtTime(t: number | null): string {
  if (t === null) return '—'
  return new Date(t * 1000).toISOString().replace('T', ' ').slice(0, 16)
}

function Stat({ label, value, sub, tone }: {
  label: string
  value: string
  sub?: string
  tone?: 'pos' | 'neg' | null
}) {
  return (
    <div className="px-4 py-3 border-r border-card-border last:border-r-0 min-w-[130px]">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn(
        'font-mono text-base font-semibold mt-0.5',
        tone === 'pos' && 'text-emerald-400',
        tone === 'neg' && 'text-red-400',
      )}>
        {value}
      </div>
      {sub && <div className="font-mono text-xs text-muted-foreground/70">{sub}</div>}
    </div>
  )
}

function Overview({ m }: { m: TesterMetrics }) {
  return (
    <div className="flex flex-wrap items-stretch divide-card-border">
      <Stat label="Net Profit" value={fmtUsd(m.net_profit)}
            sub={`${m.net_profit_pct >= 0 ? '+' : ''}${m.net_profit_pct.toFixed(2)}%`}
            tone={m.net_profit > 0 ? 'pos' : m.net_profit < 0 ? 'neg' : null} />
      <Stat label="Total Trades" value={String(m.total_trades)} />
      <Stat label="Percent Profitable"
            value={m.percent_profitable !== null ? `${m.percent_profitable.toFixed(2)}%` : '—'} />
      <Stat label="Profit Factor"
            value={m.profit_factor !== null ? m.profit_factor.toFixed(3) : '∞'}
            tone={m.profit_factor !== null ? (m.profit_factor >= 1 ? 'pos' : 'neg') : 'pos'} />
      <Stat label="Max Drawdown" value={fmtUsd(m.max_drawdown)}
            sub={`${m.max_drawdown_pct.toFixed(2)}%`} tone={m.max_drawdown > 0 ? 'neg' : null} />
      <Stat label="Avg Trade" value={fmtUsd(m.avg_trade)}
            tone={(m.avg_trade ?? 0) > 0 ? 'pos' : (m.avg_trade ?? 0) < 0 ? 'neg' : null} />
      <Stat label="Avg Win / Loss"
            value={`${fmtUsd(m.avg_win)} / ${fmtUsd(m.avg_loss)}`} />
      <Stat label="Open P&L" value={fmtUsd(m.open_pl)}
            tone={m.open_pl > 0 ? 'pos' : m.open_pl < 0 ? 'neg' : null} />
    </div>
  )
}

function EquityCurve({ result }: { result: PineBacktestResponse }) {
  const ref = useRef<HTMLDivElement>(null)
  const chart = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!ref.current) return
    const c = createChart(ref.current, {
      layout: { background: { color: '#0d1117' }, textColor: '#8b949e' },
      grid: { vertLines: { color: '#1a2332' }, horzLines: { color: '#1a2332' } },
      rightPriceScale: { borderColor: '#1a2332' },
      timeScale: { borderColor: '#1a2332', timeVisible: true },
      width: ref.current.clientWidth,
      height: ref.current.clientHeight,
    })
    chart.current = c
    const s = c.addAreaSeries({
      lineColor: '#2962FF', topColor: 'rgba(41,98,255,0.25)',
      bottomColor: 'rgba(41,98,255,0.02)', lineWidth: 2,
      priceLineVisible: false, lastValueVisible: true,
    })
    const data = result.equity
      .map((v, i) => (v !== null && result.bars[i]
        ? { time: result.bars[i].time as Time, value: v } : null))
      .filter((d): d is { time: Time; value: number } => d !== null)
    s.setData(data)
    c.timeScale().fitContent()

    const ro = new ResizeObserver(() => {
      if (ref.current) c.applyOptions({ width: ref.current.clientWidth, height: ref.current.clientHeight })
    })
    ro.observe(ref.current)
    return () => { ro.disconnect(); c.remove(); chart.current = null }
  }, [result])

  return <div ref={ref} className="h-48 w-full" />
}

function TradeList({ trades }: { trades: TradeRecord[] }) {
  return (
    <div className="overflow-auto max-h-64">
      <table className="w-full text-xs font-mono">
        <thead className="sticky top-0 bg-background">
          <tr className="text-muted-foreground border-b border-card-border">
            <th className="text-left px-3 py-2">#</th>
            <th className="text-left px-3 py-2">Dir</th>
            <th className="text-left px-3 py-2">Entry</th>
            <th className="text-left px-3 py-2">Exit</th>
            <th className="text-right px-3 py-2">Entry px</th>
            <th className="text-right px-3 py-2">Exit px</th>
            <th className="text-right px-3 py-2">Lots</th>
            <th className="text-right px-3 py-2">P&L</th>
            <th className="text-right px-3 py-2">P&L %</th>
            <th className="text-left px-3 py-2">Reason</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => (
            <tr key={i} className="border-b border-card-border/50 hover:bg-secondary/40">
              <td className="px-3 py-1.5 text-muted-foreground">{i + 1}</td>
              <td className={cn('px-3 py-1.5 font-semibold',
                t.direction === 'long' ? 'text-emerald-400' : 'text-red-400')}>
                {t.direction === 'long' ? 'LONG' : 'SHORT'}
              </td>
              <td className="px-3 py-1.5">{fmtTime(t.entry_time)}</td>
              <td className="px-3 py-1.5">{fmtTime(t.exit_time)}</td>
              <td className="px-3 py-1.5 text-right">{t.entry_price.toFixed(2)}</td>
              <td className="px-3 py-1.5 text-right">{t.exit_price?.toFixed(2) ?? '—'}</td>
              <td className="px-3 py-1.5 text-right" title={`${t.qty} oz`}>{fmtLots(t.qty)}</td>
              <td className={cn('px-3 py-1.5 text-right font-semibold',
                (t.profit ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                {fmtUsd(t.profit)}
              </td>
              <td className="px-3 py-1.5 text-right text-muted-foreground">
                {t.profit_pct !== null ? `${t.profit_pct.toFixed(2)}%` : '—'}
              </td>
              <td className="px-3 py-1.5 text-muted-foreground">{t.exit_reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {trades.length === 0 && (
        <div className="text-center text-muted-foreground text-sm py-6">No closed trades</div>
      )}
    </div>
  )
}

const TABS = ['Overview', 'Equity Curve', 'List of Trades'] as const

export function StrategyTester({ result }: { result: PineBacktestResponse | null }) {
  const [tab, setTab] = useState<(typeof TABS)[number]>('Overview')

  if (!result || !result.ok) return null
  if (result.script_type !== 'strategy') {
    return (
      <div className="px-4 py-3 text-sm text-muted-foreground border-t border-card-border">
        Indicator script — no strategy tester. Use <code className="text-accent">strategy()</code> to backtest.
      </div>
    )
  }
  if (!result.metrics) return null

  return (
    <div className="border-t border-card-border bg-background">
      <div className="flex items-center gap-1 px-3 pt-2 border-b border-card-border">
        <span className="text-xs font-semibold text-foreground mr-3 pb-2">Strategy Tester</span>
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              'text-xs px-3 pb-2 border-b-2 -mb-px transition-colors',
              tab === t
                ? 'border-accent text-accent'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {t}
          </button>
        ))}
        <span className="ml-auto text-xs text-muted-foreground pb-2">
          {result.title}
        </span>
      </div>
      {tab === 'Overview' && <Overview m={result.metrics} />}
      {tab === 'Equity Curve' && <EquityCurve result={result} />}
      {tab === 'List of Trades' && <TradeList trades={result.trades} />}
    </div>
  )
}
