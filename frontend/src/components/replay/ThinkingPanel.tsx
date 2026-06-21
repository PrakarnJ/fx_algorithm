import React from 'react'
import type { ReplayFrame } from '@/lib/api'
import type { SessionSummary } from './ChartPlayer'
import { formatPrice, formatPts } from '@/lib/formatters'

interface ThinkingPanelProps {
  frame: ReplayFrame | null
  summary: SessionSummary
}

export function ThinkingPanel({ frame, summary }: ThinkingPanelProps) {
  const totalTrades = summary.wins + summary.losses
  const winRate = totalTrades > 0 ? ((summary.wins / totalTrades) * 100).toFixed(1) : '—'

  if (!frame) {
    return (
      <div className="h-full flex items-center justify-center text-muted-foreground font-mono text-xs">
        Load a session to begin
      </div>
    )
  }

  const { bar_time, bar, signal, open_trade, trade_closed, indicator_snapshot } = frame

  return (
    <div className="h-full overflow-y-auto font-mono text-xs p-3 space-y-3">

      {/* Session Summary */}
      <div className="border border-card-border rounded p-2 bg-secondary/10">
        <div className="text-muted-foreground uppercase tracking-wider text-xs mb-1">
          Session Summary
        </div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
          <span className="text-muted-foreground">P&amp;L</span>
          <span className={summary.totalPts >= 0 ? 'text-buy' : 'text-sell'}>
            {formatPts(summary.totalPts)} pts
          </span>
          <span className="text-muted-foreground">Trades</span>
          <span className="text-foreground">{totalTrades}</span>
          <span className="text-muted-foreground">Win / Loss</span>
          <span className="text-foreground">{summary.wins} / {summary.losses}</span>
          <span className="text-muted-foreground">Win Rate</span>
          <span className="text-foreground">{winRate}{totalTrades > 0 ? '%' : ''}</span>
        </div>
      </div>
      {/* Bar time */}
      <div>
        <div className="text-muted-foreground uppercase tracking-wider text-xs mb-1">
          Bar Time
        </div>
        <div className="text-accent">{bar_time}</div>
      </div>

      {/* Current bar OHLC */}
      <div>
        <div className="text-muted-foreground uppercase tracking-wider text-xs mb-1">
          OHLC
        </div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-foreground">
          <span className="text-muted-foreground">O</span>
          <span>{formatPrice(bar.open)}</span>
          <span className="text-muted-foreground">H</span>
          <span className="text-buy">{formatPrice(bar.high)}</span>
          <span className="text-muted-foreground">L</span>
          <span className="text-sell">{formatPrice(bar.low)}</span>
          <span className="text-muted-foreground">C</span>
          <span>{formatPrice(bar.close)}</span>
        </div>
      </div>

      {/* Indicator snapshot */}
      {Object.keys(indicator_snapshot).length > 0 && (
        <div>
          <div className="text-muted-foreground uppercase tracking-wider text-xs mb-1">
            Indicators
          </div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
            {Object.entries(indicator_snapshot).map(([k, v]) => (
              <React.Fragment key={k}>
                <span className="text-muted-foreground truncate" title={k}>{k}</span>
                <span className="text-foreground">
                  {typeof v === 'number' ? v.toFixed(4) : String(v)}
                </span>
              </React.Fragment>
            ))}
          </div>
        </div>
      )}

      {/* Signal */}
      {signal && (
        <div className="border border-accent/30 bg-accent/5 rounded p-2">
          <div className="text-accent uppercase tracking-wider text-xs mb-1 font-bold">
            Signal
          </div>
          <div
            className={`text-sm font-bold mb-1 ${
              signal.direction === 'buy' ? 'text-buy' : 'text-sell'
            }`}
          >
            {signal.direction} @ {formatPrice(signal.entry_price)}
          </div>
          <div className="text-muted-foreground space-y-0.5">
            <div>SL: <span className="text-sell">{formatPrice(signal.sl)}</span></div>
            <div>TP: <span className="text-buy">{formatPrice(signal.tp)}</span></div>
            <div>ATR: <span className="text-foreground">{signal.atr.toFixed(4)}</span></div>
          </div>
        </div>
      )}

      {/* Open trade */}
      {open_trade && (
        <div className="border border-card-border bg-secondary/20 rounded p-2">
          <div className="text-muted-foreground uppercase tracking-wider text-xs mb-1">
            Open Trade
          </div>
          <div
            className={`text-sm font-bold mb-1 ${
              open_trade.direction === 'buy' ? 'text-buy' : 'text-sell'
            }`}
          >
            {open_trade.direction}
          </div>
          <div className="text-muted-foreground space-y-0.5">
            <div>Entry: <span className="text-foreground">{formatPrice(open_trade.entry_price)}</span></div>
            <div>SL: <span className="text-sell">{formatPrice(open_trade.sl)}</span></div>
            <div>TP: <span className="text-buy">{formatPrice(open_trade.tp)}</span></div>
            <div>Bars: <span className="text-foreground">{open_trade.open_bars}</span></div>
          </div>
        </div>
      )}

      {/* Trade closed */}
      {trade_closed && (
        <div
          className={`border rounded p-2 ${
            trade_closed.profit_pts >= 0
              ? 'border-buy/30 bg-buy/5'
              : 'border-sell/30 bg-sell/5'
          }`}
        >
          <div className="text-muted-foreground uppercase tracking-wider text-xs mb-1">
            Trade Closed
          </div>
          <div
            className={`text-sm font-bold ${
              trade_closed.profit_pts >= 0 ? 'text-buy' : 'text-sell'
            }`}
          >
            TRADE CLOSED: {formatPts(trade_closed.profit_pts)} pts ({trade_closed.outcome})
          </div>
        </div>
      )}
    </div>
  )
}
