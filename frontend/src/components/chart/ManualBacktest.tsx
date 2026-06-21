import { useState, useEffect, useCallback } from 'react'
import { ChevronLeft, ChevronRight, TrendingUp, TrendingDown, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { OHLCBar } from '@/lib/api'

interface ManualTrade {
  direction: 'buy' | 'sell'
  entryPrice: number
  entryTime: number
  sl: number
  tp: number
  exitPrice?: number
  exitTime?: number
  profitPts?: number
}

interface Props {
  bars: OHLCBar[]
  currentIndex: number
  onIndexChange: (idx: number) => void
}

export function ManualBacktest({ bars, currentIndex, onIndexChange }: Props) {
  const [openTrade, setOpenTrade] = useState<ManualTrade | null>(null)
  const [closedTrades, setClosedTrades] = useState<ManualTrade[]>([])
  const [entryForm, setEntryForm] = useState<{ dir: 'buy' | 'sell'; sl: string; tp: string } | null>(null)
  const [showJournal, setShowJournal] = useState(false)

  const bar = bars[currentIndex]

  const next = useCallback(() => {
    if (currentIndex < bars.length - 1) onIndexChange(currentIndex + 1)
  }, [currentIndex, bars.length, onIndexChange])

  const prev = useCallback(() => {
    if (currentIndex > 0) onIndexChange(currentIndex - 1)
  }, [currentIndex, onIndexChange])

  // Keyboard navigation
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement) return
      if (e.key === 'ArrowRight') next()
      if (e.key === 'ArrowLeft') prev()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [next, prev])

  // Check SL/TP on bar advance
  useEffect(() => {
    if (!openTrade || !bar) return
    const { direction, sl, tp } = openTrade
    const hitSL = direction === 'buy' ? bar.low <= sl : bar.high >= sl
    const hitTP = direction === 'buy' ? bar.high >= tp : bar.low <= tp

    if (hitSL || hitTP) {
      const exitPrice = hitSL ? sl : tp
      const profitPts = direction === 'buy'
        ? (exitPrice - openTrade.entryPrice) / 0.01
        : (openTrade.entryPrice - exitPrice) / 0.01
      const closed: ManualTrade = { ...openTrade, exitPrice, exitTime: bar.time, profitPts }
      setClosedTrades(prev => [...prev, closed])
      setOpenTrade(null)
    }
  }, [currentIndex]) // eslint-disable-line react-hooks/exhaustive-deps

  function enterTrade(dir: 'buy' | 'sell') {
    setEntryForm({ dir, sl: '', tp: '' })
  }

  function confirmEntry() {
    if (!entryForm || !bar) return
    const sl = parseFloat(entryForm.sl)
    const tp = parseFloat(entryForm.tp)
    if (isNaN(sl) || isNaN(tp)) return
    setOpenTrade({
      direction: entryForm.dir,
      entryPrice: bar.close,
      entryTime: bar.time,
      sl,
      tp,
    })
    setEntryForm(null)
  }

  function closeManually() {
    if (!openTrade || !bar) return
    const profitPts = openTrade.direction === 'buy'
      ? (bar.close - openTrade.entryPrice) / 0.01
      : (openTrade.entryPrice - bar.close) / 0.01
    setClosedTrades(prev => [...prev, { ...openTrade, exitPrice: bar.close, exitTime: bar.time, profitPts }])
    setOpenTrade(null)
  }

  const totalPts = closedTrades.reduce((s, t) => s + (t.profitPts ?? 0), 0)
  const wins = closedTrades.filter(t => (t.profitPts ?? 0) > 0).length
  const barTime = bar ? new Date(bar.time * 1000).toISOString().replace('T', ' ').slice(0, 16) : '—'

  return (
    <div className="border-t border-card-border bg-background">
      {/* Controls row */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-card-border/50">
        <Button size="icon" variant="outline" className="h-7 w-7" onClick={prev} disabled={currentIndex === 0}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <Button size="icon" variant="outline" className="h-7 w-7" onClick={next} disabled={currentIndex >= bars.length - 1}>
          <ChevronRight className="h-4 w-4" />
        </Button>
        <span className="font-mono text-xs text-muted-foreground">
          Bar <span className="text-foreground">{currentIndex + 1}</span> / {bars.length}
          <span className="mx-2">·</span>
          <span className="text-foreground">{barTime}</span>
        </span>

        {!openTrade && !entryForm && (
          <>
            <Button
              size="sm"
              variant="outline"
              className="h-7 px-2 text-xs text-buy border-buy/50 hover:bg-buy/10 ml-2"
              onClick={() => enterTrade('buy')}
            >
              <TrendingUp className="h-3 w-3 mr-1" /> Buy
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7 px-2 text-xs text-sell border-sell/50 hover:bg-sell/10"
              onClick={() => enterTrade('sell')}
            >
              <TrendingDown className="h-3 w-3 mr-1" /> Sell
            </Button>
          </>
        )}

        {entryForm && (
          <div className="flex items-center gap-2 ml-2">
            <span className={`font-mono text-xs font-bold ${entryForm.dir === 'buy' ? 'text-buy' : 'text-sell'}`}>
              {entryForm.dir.toUpperCase()} @ {bar?.close.toFixed(2)}
            </span>
            <span className="font-mono text-xs text-muted-foreground">SL</span>
            <input
              type="number"
              step="0.01"
              placeholder="Stop Loss"
              value={entryForm.sl}
              onChange={e => setEntryForm(f => f ? { ...f, sl: e.target.value } : f)}
              className="w-24 h-6 px-2 text-xs font-mono bg-secondary border border-card-border rounded text-foreground focus:outline-none focus:border-accent"
            />
            <span className="font-mono text-xs text-muted-foreground">TP</span>
            <input
              type="number"
              step="0.01"
              placeholder="Take Profit"
              value={entryForm.tp}
              onChange={e => setEntryForm(f => f ? { ...f, tp: e.target.value } : f)}
              className="w-24 h-6 px-2 text-xs font-mono bg-secondary border border-card-border rounded text-foreground focus:outline-none focus:border-accent"
            />
            <Button size="sm" className="h-6 px-2 text-xs" onClick={confirmEntry}>Enter</Button>
            <button className="text-muted-foreground hover:text-foreground" onClick={() => setEntryForm(null)}>
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        {openTrade && (
          <div className="flex items-center gap-3 ml-2">
            <span className={`font-mono text-xs font-bold ${openTrade.direction === 'buy' ? 'text-buy' : 'text-sell'}`}>
              {openTrade.direction.toUpperCase()}
            </span>
            <span className="font-mono text-xs text-muted-foreground">
              @ {openTrade.entryPrice.toFixed(2)}
              <span className="mx-1">SL</span>
              <span className="text-sell">{openTrade.sl.toFixed(2)}</span>
              <span className="mx-1">TP</span>
              <span className="text-buy">{openTrade.tp.toFixed(2)}</span>
            </span>
            {bar && (
              <span className={`font-mono text-xs font-semibold ${
                (openTrade.direction === 'buy' ? bar.close - openTrade.entryPrice : openTrade.entryPrice - bar.close) >= 0
                  ? 'text-buy'
                  : 'text-sell'
              }`}>
                {((openTrade.direction === 'buy'
                  ? bar.close - openTrade.entryPrice
                  : openTrade.entryPrice - bar.close) / 0.01).toFixed(1)} pts
              </span>
            )}
            <Button
              size="sm"
              variant="outline"
              className="h-6 px-2 text-xs"
              onClick={closeManually}
            >
              Close
            </Button>
          </div>
        )}

        <div className="ml-auto flex items-center gap-3">
          <span className={`font-mono text-xs font-semibold ${totalPts >= 0 ? 'text-buy' : 'text-sell'}`}>
            {totalPts >= 0 ? '+' : ''}{totalPts.toFixed(1)} pts
          </span>
          <span className="font-mono text-xs text-muted-foreground">
            {wins}/{closedTrades.length} trades
          </span>
          <Button
            size="sm"
            variant="outline"
            className="h-7 px-2 text-xs"
            onClick={() => setShowJournal(j => !j)}
          >
            Journal
          </Button>
        </div>
      </div>

      {/* Journal */}
      {showJournal && closedTrades.length > 0 && (
        <div className="max-h-36 overflow-y-auto border-t border-card-border/30">
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="border-b border-card-border/30 text-muted-foreground">
                <th className="px-3 py-1 text-left">#</th>
                <th className="px-3 py-1 text-left">Dir</th>
                <th className="px-3 py-1 text-right">Entry</th>
                <th className="px-3 py-1 text-right">Exit</th>
                <th className="px-3 py-1 text-right">P&L (pts)</th>
                <th className="px-3 py-1 text-left">Result</th>
              </tr>
            </thead>
            <tbody>
              {closedTrades.map((t, i) => (
                <tr key={i} className="border-b border-card-border/20 hover:bg-secondary/10">
                  <td className="px-3 py-1 text-muted-foreground">{i + 1}</td>
                  <td className={`px-3 py-1 font-bold ${t.direction === 'buy' ? 'text-buy' : 'text-sell'}`}>
                    {t.direction.toUpperCase()}
                  </td>
                  <td className="px-3 py-1 text-right">{t.entryPrice.toFixed(2)}</td>
                  <td className="px-3 py-1 text-right">{t.exitPrice?.toFixed(2) ?? '—'}</td>
                  <td className={`px-3 py-1 text-right font-semibold ${(t.profitPts ?? 0) >= 0 ? 'text-buy' : 'text-sell'}`}>
                    {(t.profitPts ?? 0) >= 0 ? '+' : ''}{(t.profitPts ?? 0).toFixed(1)}
                  </td>
                  <td className={`px-3 py-1 ${(t.profitPts ?? 0) >= 0 ? 'text-buy' : 'text-sell'}`}>
                    {(t.profitPts ?? 0) >= 0 ? 'WIN' : 'LOSS'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
