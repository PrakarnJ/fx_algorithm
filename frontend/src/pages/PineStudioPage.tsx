import { useCallback, useEffect, useState } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { javascript } from '@codemirror/lang-javascript'
import { oneDark } from '@codemirror/theme-one-dark'
import { Play, LoaderCircle } from 'lucide-react'
import { PineChart } from '@/components/pine/PineChart'
import { StrategyTester } from '@/components/pine/StrategyTester'
import { useChartInfo } from '@/hooks/useApi'
import { runPineBacktest, type PineBacktestResponse } from '@/lib/api'
import { cn } from '@/lib/utils'

const DEFAULT_SCRIPT = `//@version=6
strategy("EMA Cross", overlay=true, initial_capital=100000, default_qty_value=10)

fastLen = input.int(9, title="Fast EMA")
slowLen = input.int(21, title="Slow EMA")

fast = ta.ema(close, fastLen)
slow = ta.ema(close, slowLen)

plot(fast, "Fast EMA", color.orange)
plot(slow, "Slow EMA", color.blue)

longCond = ta.crossover(fast, slow)
shortCond = ta.crossunder(fast, slow)

if longCond
    strategy.entry("L", strategy.long)
if shortCond
    strategy.entry("S", strategy.short)
`

const STORAGE_KEY = 'pine-studio-script'
const TIMEFRAMES = ['M15', 'H1', 'H4']

export function PineStudioPage() {
  const [source, setSource] = useState<string>(
    () => localStorage.getItem(STORAGE_KEY) ?? DEFAULT_SCRIPT,
  )
  const [timeframe, setTimeframe] = useState('H1')
  const [startDate, setStartDate] = useState('2025-01-01')
  const [endDate, setEndDate] = useState('')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<PineBacktestResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { data: info } = useChartInfo()

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, source)
  }, [source])

  const run = useCallback(async () => {
    setRunning(true)
    setError(null)
    try {
      const res = await runPineBacktest({
        source,
        timeframe,
        start_date: startDate || null,
        end_date: endDate || null,
      })
      setResult(res)
      if (!res.ok && res.errors.length > 0) {
        const e = res.errors[0]
        setError(`Line ${e.line}:${e.col} — ${e.message}`)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(false)
    }
  }, [source, timeframe, startDate, endDate])

  // Ctrl/Cmd+Enter runs the script
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault()
        void run()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [run])

  const tfInfo = info?.timeframes?.[timeframe]

  return (
    <div className="flex flex-col h-screen">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-card-border">
        <span className="font-mono text-sm font-bold text-accent">XAUUSD</span>
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
        {tfInfo && (
          <span className="text-xs text-muted-foreground font-mono">
            {tfInfo.bars.toLocaleString()} bars · {tfInfo.start} → {tfInfo.end}
          </span>
        )}
        <button
          onClick={() => void run()}
          disabled={running}
          className="ml-auto flex items-center gap-2 bg-accent/15 text-accent border border-accent/30
                     rounded-md px-4 py-1.5 text-sm font-semibold hover:bg-accent/25
                     disabled:opacity-50 transition-colors"
        >
          {running
            ? <LoaderCircle className="h-4 w-4 animate-spin" />
            : <Play className="h-4 w-4" />}
          {running ? 'Running…' : 'Run'}
          <span className="text-xs text-muted-foreground font-mono">⌘⏎</span>
        </button>
      </div>

      {/* Editor | Chart */}
      <div className="flex flex-1 min-h-0">
        <div className="w-[420px] flex-shrink-0 border-r border-card-border flex flex-col min-h-0">
          <div className="px-3 py-1.5 text-xs text-muted-foreground border-b border-card-border">
            Pine Script <span className="text-muted-foreground/60">(v4–v6 subset)</span>
          </div>
          <div className="flex-1 overflow-auto">
            <CodeMirror
              value={source}
              onChange={setSource}
              theme={oneDark}
              extensions={[javascript()]}
              basicSetup={{ lineNumbers: true, foldGutter: false, highlightActiveLine: true }}
              style={{ fontSize: 13, height: '100%' }}
            />
          </div>
          {error && (
            <div className="px-3 py-2 text-xs font-mono text-red-400 bg-red-950/40 border-t border-red-900/50 whitespace-pre-wrap">
              {error}
            </div>
          )}
        </div>
        <div className="flex-1 min-w-0 flex flex-col">
          {result && result.ok ? (
            <PineChart result={result} />
          ) : (
            <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">
              {running ? 'Running backtest…' : 'Paste a Pine Script and press Run (⌘⏎)'}
            </div>
          )}
        </div>
      </div>

      {/* Strategy Tester */}
      <StrategyTester result={result} />
    </div>
  )
}
