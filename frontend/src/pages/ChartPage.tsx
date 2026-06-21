import { useState, useMemo } from 'react'
import { Settings, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { TradingChart } from '@/components/chart/TradingChart'
import { IndicatorConfig, DEFAULT_INDICATORS } from '@/components/chart/IndicatorConfig'
import { ManualBacktest } from '@/components/chart/ManualBacktest'
import { useStocks, useStockBars } from '@/hooks/useApi'
import type { IndicatorSettings } from '@/components/chart/IndicatorConfig'

const TF_OPTIONS = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1']
const LIMIT = 10000

export function ChartPage() {
  const { data: stocks } = useStocks()

  const [symbol, setSymbol] = useState<string>('')
  const [tf, setTf] = useState('H1')
  const [indicators, setIndicators] = useState<IndicatorSettings>(DEFAULT_INDICATORS)
  const [showIndicators, setShowIndicators] = useState(false)
  const [manualMode, setManualMode] = useState(false)
  const [manualIndex, setManualIndex] = useState(0)

  const { data: barsData, isLoading, error } = useStockBars(symbol || null, tf, LIMIT)
  const bars = useMemo(() => barsData?.bars ?? [], [barsData])

  // When we enter manual mode, start from bar 0 (hide future)
  function toggleManual() {
    if (!manualMode) setManualIndex(0)
    setManualMode(m => !m)
  }

  // Reset manual index when data changes
  const currentBarIndex = manualMode ? manualIndex : null

  // Get available TFs for selected symbol
  const availableTFs = useMemo(() => {
    const stock = stocks?.find(s => s.symbol === symbol)
    return stock?.available_tfs ?? TF_OPTIONS
  }, [stocks, symbol])

  return (
    <div className="flex flex-col h-screen relative">
      {/* Top bar */}
      <div className="flex items-center gap-3 px-4 py-2.5 border-b border-card-border bg-background flex-shrink-0">
        <span className="font-mono text-xs text-accent uppercase tracking-wider mr-1">Chart</span>

        <Select value={symbol} onValueChange={v => { setSymbol(v); setManualIndex(0) }}>
          <SelectTrigger className="w-36 h-8 text-xs">
            <SelectValue placeholder="Symbol…" />
          </SelectTrigger>
          <SelectContent>
            {(stocks ?? []).map(s => (
              <SelectItem key={s.symbol} value={s.symbol} className="text-xs font-mono">
                {s.symbol}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={tf} onValueChange={v => { setTf(v); setManualIndex(0) }}>
          <SelectTrigger className="w-24 h-8 text-xs">
            <SelectValue placeholder="TF…" />
          </SelectTrigger>
          <SelectContent>
            {availableTFs.map(t => (
              <SelectItem key={t} value={t} className="text-xs font-mono">{t}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        {bars.length > 0 && (
          <span className="font-mono text-xs text-muted-foreground">
            {bars.length.toLocaleString()} bars
          </span>
        )}

        <div className="ml-auto flex items-center gap-2">
          {/* Manual Backtest toggle */}
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">Manual BT</span>
            <button
              onClick={toggleManual}
              className={`w-10 h-5 rounded-full transition-colors relative ${
                manualMode ? 'bg-accent' : 'bg-secondary'
              }`}
            >
              <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-all ${
                manualMode ? 'left-5' : 'left-0.5'
              }`} />
            </button>
          </div>

          <Button
            size="sm"
            variant={showIndicators ? 'default' : 'outline'}
            className="h-8 px-3 text-xs gap-1.5"
            onClick={() => setShowIndicators(v => !v)}
          >
            <Settings className="h-3.5 w-3.5" />
            Indicators
          </Button>
        </div>
      </div>

      {/* Main content area */}
      <div className="flex-1 overflow-hidden relative" style={{ minHeight: 0 }}>
        {!symbol ? (
          <div className="h-full flex items-center justify-center text-muted-foreground font-mono text-sm">
            <div className="text-center">
              <div className="text-4xl text-accent mb-3">_</div>
              Select a symbol to load the chart.
            </div>
          </div>
        ) : isLoading ? (
          <div className="h-full flex items-center justify-center gap-3 text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin text-accent" />
            <span className="font-mono text-sm">Loading {symbol} {tf}…</span>
          </div>
        ) : error ? (
          <div className="h-full flex items-center justify-center font-mono text-sm text-sell">
            Failed to load data. Download {symbol} {tf} data first.
          </div>
        ) : bars.length === 0 ? (
          <div className="h-full flex items-center justify-center font-mono text-sm text-muted-foreground">
            No {tf} data for {symbol}. Go to Data → download it first.
          </div>
        ) : (
          <div className="flex flex-col h-full">
            <div className={`flex-1 ${manualMode ? '' : 'h-full'}`} style={{ minHeight: 0 }}>
              <TradingChart
                bars={bars}
                indicators={indicators}
                currentBarIndex={currentBarIndex}
              />
            </div>

            {manualMode && (
              <ManualBacktest
                bars={bars}
                currentIndex={manualIndex}
                onIndexChange={setManualIndex}
              />
            )}
          </div>
        )}

        {/* Indicator config panel — slides in from right */}
        {showIndicators && (
          <IndicatorConfig
            value={indicators}
            onChange={setIndicators}
            onClose={() => setShowIndicators(false)}
          />
        )}
      </div>
    </div>
  )
}
