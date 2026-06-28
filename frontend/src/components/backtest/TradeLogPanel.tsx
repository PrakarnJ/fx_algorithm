import { useState, useMemo } from 'react'
import type { BacktestResult, Trade } from '@/lib/api'

interface TradeRow {
  idx: number
  trade: Trade
  qty: number
  profitUsd: number
  balance: number
}

function computeRows(
  trades: Trade[],
  tickSize: number,
  capital: number,
  riskPct: number,
): TradeRow[] {
  const riskAmount = capital * (riskPct / 100)
  let balance = capital
  return trades.map((t, i) => {
    // Use initial_sl (entry stop) for sizing — t.sl may have trailed during the trade
    const initialSl = t.initial_sl ?? t.sl
    const slDist = Math.abs(t.entry_price - initialSl)
    const qty = slDist > 0 ? riskAmount / slDist : 0
    const profitUsd = (t.profit_pips ?? 0) * tickSize * qty
    balance += profitUsd
    return { idx: i + 1, trade: t, qty, profitUsd, balance }
  })
}

function fmtDate(iso: string): string {
  const d = new Date(iso)
  const mo = String(d.getMonth() + 1).padStart(2, '0')
  const da = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${mo}/${da} ${hh}:${mm}`
}

function fmtPrice(n: number | null | undefined, decimals = 2): string {
  if (n == null) return '—'
  return n.toFixed(decimals)
}

function fmtTp(tp: number | null | undefined, decimals = 2): string {
  if (tp == null) return '—'
  // FAR_TP = ±1e6 means trailing stop governs exit (no fixed TP)
  if (Math.abs(tp) > 100_000) return 'TRAIL'
  return tp.toFixed(decimals)
}

function fmtUsd(n: number): string {
  const sign = n >= 0 ? '+' : ''
  return `${sign}$${Math.abs(n).toFixed(2)}`
}

function ExitBadge({ reason }: { reason: string }) {
  const cfg: Record<string, { label: string; cls: string }> = {
    tp:    { label: 'TP',    cls: 'bg-buy/20 text-buy' },
    trail: { label: 'TRAIL', cls: 'bg-accent/20 text-accent' },
    sl:    { label: 'SL',    cls: 'bg-sell/20 text-sell' },
    time:  { label: 'TIME',  cls: 'bg-muted/40 text-muted-foreground' },
    eod:   { label: 'EOD',   cls: 'bg-muted/40 text-muted-foreground' },
  }
  const { label, cls } = cfg[reason] ?? { label: reason.toUpperCase() || '—', cls: 'bg-muted/20 text-muted-foreground' }
  return <span className={`px-1.5 py-0.5 rounded text-xs font-semibold ${cls}`}>{label}</span>
}

interface TradeLogPanelProps {
  result: BacktestResult
  tickSize: number
}

export function TradeLogPanel({ result, tickSize }: TradeLogPanelProps) {
  const [capital, setCapital] = useState(() => Number(localStorage.getItem('tl_capital') ?? 1000))
  const [riskPct, setRiskPct] = useState(() => Number(localStorage.getItem('tl_risk_pct') ?? 2))

  const rows = useMemo(
    () => computeRows(result.trades, tickSize, capital, riskPct),
    [result.trades, tickSize, capital, riskPct],
  )

  // Summary metrics
  const finalBalance = rows.length > 0 ? rows[rows.length - 1].balance : capital
  const returnPct = ((finalBalance - capital) / capital) * 100
  const wins = rows.filter(r => (r.trade.profit_pips ?? 0) > 0).length
  const winRate = rows.length > 0 ? (wins / rows.length) * 100 : 0

  // Max drawdown in $
  let peak = capital
  let maxDd = 0
  for (const r of rows) {
    if (r.balance > peak) peak = r.balance
    const dd = peak - r.balance
    if (dd > maxDd) maxDd = dd
  }

  // Equity curve: normalise balances to 0–100% height
  const balances = [capital, ...rows.map(r => r.balance)]
  const balMin = Math.min(...balances)
  const balMax = Math.max(...balances)
  const balRange = balMax - balMin || 1

  // Decimal places for price display
  const pDec = tickSize < 0.001 ? 5 : tickSize < 0.1 ? 2 : 2

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Controls */}
      <div className="flex items-center gap-4 px-4 py-2.5 border-b border-card-border flex-shrink-0 bg-secondary/10 font-mono text-xs">
        <span className="text-muted-foreground">Capital</span>
        <div className="flex items-center gap-1">
          <span className="text-muted-foreground">$</span>
          <input
            type="number"
            min={10}
            step={100}
            value={capital}
            onChange={e => { const v = Math.max(10, Number(e.target.value)); setCapital(v); localStorage.setItem('tl_capital', String(v)) }}
            className="w-20 h-6 px-1.5 bg-secondary border border-card-border rounded text-foreground focus:outline-none focus:border-accent"
          />
        </div>
        <span className="text-muted-foreground">Risk</span>
        <div className="flex items-center gap-1">
          <input
            type="number"
            min={0.1}
            max={10}
            step={0.5}
            value={riskPct}
            onChange={e => { const v = Math.max(0.1, Math.min(10, Number(e.target.value))); setRiskPct(v); localStorage.setItem('tl_risk_pct', String(v)) }}
            className="w-14 h-6 px-1.5 bg-secondary border border-card-border rounded text-foreground focus:outline-none focus:border-accent"
          />
          <span className="text-muted-foreground">%</span>
        </div>
        <span className="text-muted-foreground ml-auto">
          {result.trades.length} trades · tick {tickSize}
        </span>
      </div>

      {/* Summary strip */}
      <div className="grid grid-cols-4 gap-px border-b border-card-border flex-shrink-0">
        {[
          {
            label: 'Final Balance',
            value: `$${finalBalance.toFixed(2)}`,
            color: finalBalance >= capital ? 'text-buy' : 'text-sell',
          },
          {
            label: 'Return',
            value: `${returnPct >= 0 ? '+' : ''}${returnPct.toFixed(1)}%`,
            color: returnPct >= 0 ? 'text-buy' : 'text-sell',
          },
          {
            label: 'Win Rate',
            value: `${winRate.toFixed(0)}%`,
            color: winRate >= 50 ? 'text-buy' : 'text-sell',
          },
          {
            label: 'Max Drawdown',
            value: `-$${maxDd.toFixed(2)}`,
            color: 'text-sell',
          },
        ].map(m => (
          <div key={m.label} className="px-3 py-2 bg-secondary/5">
            <div className="text-xs text-muted-foreground font-mono mb-0.5">{m.label}</div>
            <div className={`text-sm font-mono font-semibold ${m.color}`}>{m.value}</div>
          </div>
        ))}
      </div>

      {/* Equity curve */}
      {rows.length > 0 && (
        <div className="flex-shrink-0 px-4 py-2 border-b border-card-border">
          <div className="text-xs text-muted-foreground font-mono mb-1.5">Equity Curve</div>
          <div className="flex items-end gap-px h-12">
            {rows.map(r => {
              const heightPct = ((r.balance - balMin) / balRange) * 100
              const isWin = (r.trade.profit_pips ?? 0) > 0
              return (
                <div
                  key={r.idx}
                  title={`#${r.idx}: $${r.balance.toFixed(2)}`}
                  className={`flex-1 min-w-[2px] rounded-sm transition-opacity hover:opacity-70 ${isWin ? 'bg-buy' : 'bg-sell'}`}
                  style={{ height: `${Math.max(4, heightPct)}%` }}
                />
              )
            })}
          </div>
        </div>
      )}

      {/* Trade table */}
      {rows.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-muted-foreground font-mono text-sm">
          No trades in this result.
        </div>
      ) : (
        <div className="flex-1 overflow-auto">
          <table className="w-full text-xs font-mono">
            <thead className="sticky top-0 bg-background z-10">
              <tr className="border-b border-card-border">
                {['#', 'Date', 'B/S', 'Entry', 'SL', 'TP', 'Exit', 'How', 'Qty', 'P&L', 'Balance'].map(h => (
                  <th
                    key={h}
                    className="px-2 py-2 text-left text-muted-foreground font-normal tracking-wider whitespace-nowrap"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(r => {
                const win = (r.trade.profit_pips ?? 0) > 0
                const isBuy = r.trade.direction === 'buy'
                return (
                  <tr
                    key={r.idx}
                    className="border-b border-card-border/40 hover:bg-secondary/20 transition-colors"
                  >
                    <td className="px-2 py-1.5 text-muted-foreground">{r.idx}</td>
                    <td className="px-2 py-1.5 text-foreground whitespace-nowrap">
                      {fmtDate(r.trade.entry_time)}
                    </td>
                    <td className="px-2 py-1.5">
                      <span
                        className={`px-1.5 py-0.5 rounded text-xs font-semibold ${
                          isBuy ? 'bg-buy/20 text-buy' : 'bg-sell/20 text-sell'
                        }`}
                      >
                        {isBuy ? 'BUY' : 'SELL'}
                      </span>
                    </td>
                    <td className="px-2 py-1.5 text-foreground">{fmtPrice(r.trade.entry_price, pDec)}</td>
                    <td className="px-2 py-1.5 text-sell" title="Initial stop loss (entry risk)">{fmtPrice(r.trade.initial_sl ?? r.trade.sl, pDec)}</td>
                    <td className="px-2 py-1.5 text-buy">{fmtTp(r.trade.tp, pDec)}</td>
                    <td className="px-2 py-1.5 text-foreground">
                      {r.trade.exit_price != null ? fmtPrice(r.trade.exit_price, pDec) : '—'}
                    </td>
                    <td className="px-2 py-1.5">
                      <ExitBadge reason={r.trade.exit_reason ?? ''} />
                    </td>
                    <td className="px-2 py-1.5 text-accent">
                      {r.qty > 0 ? `${r.qty.toFixed(2)}` : '—'}
                    </td>
                    <td className={`px-2 py-1.5 font-semibold ${win ? 'text-buy' : 'text-sell'}`}>
                      {fmtUsd(r.profitUsd)}
                    </td>
                    <td className="px-2 py-1.5 text-foreground">
                      ${r.balance.toFixed(2)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
