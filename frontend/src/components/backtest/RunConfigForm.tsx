import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { TerminalCard } from '@/components/shared/TerminalCard'
import { useAlgorithms, useStocks } from '@/hooks/useApi'
import { apiFetch } from '@/lib/api'
import { Loader2 } from 'lucide-react'

interface RunConfigFormProps {
  onJobStarted: (jobId: string) => void
}

export function RunConfigForm({ onJobStarted }: RunConfigFormProps) {
  const { data: algos, isLoading: loadingAlgos } = useAlgorithms()
  const { data: stocks, isLoading: loadingStocks } = useStocks()
  const [selectedAlgos, setSelectedAlgos] = useState<Set<string>>(new Set())
  const [selectedSymbols, setSelectedSymbols] = useState<Set<string>>(new Set())
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function toggleAlgo(name: string) {
    setSelectedAlgos(prev => {
      const next = new Set(prev)
      next.has(name) ? next.delete(name) : next.add(name)
      return next
    })
  }

  function toggleSymbol(symbol: string) {
    setSelectedSymbols(prev => {
      const next = new Set(prev)
      next.has(symbol) ? next.delete(symbol) : next.add(symbol)
      return next
    })
  }

  function selectAllAlgos() {
    if (!algos) return
    setSelectedAlgos(new Set(algos.map(a => a.name)))
  }

  function selectAllSymbols() {
    if (!stocks) return
    setSelectedSymbols(new Set(stocks.map(s => s.symbol)))
  }

  async function handleRun() {
    if (selectedAlgos.size === 0 || selectedSymbols.size === 0) {
      setError('Select at least one algorithm and one symbol.')
      return
    }
    setError(null)
    setRunning(true)
    try {
      const res = await apiFetch<{ job_id: string }>('/api/backtest/run', {
        method: 'POST',
        body: JSON.stringify({
          algo_names: Array.from(selectedAlgos),
          symbols: Array.from(selectedSymbols),
          start_date: startDate || null,
          end_date: endDate || null,
        }),
      })
      onJobStarted(res.job_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start backtest')
    } finally {
      setRunning(false)
    }
  }

  return (
    <TerminalCard title="Configure Backtest">
      <div className="space-y-6">
        {/* Algorithms */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <span className="font-mono text-xs text-muted-foreground uppercase tracking-wider">
              Algorithms
            </span>
            <button
              onClick={selectAllAlgos}
              className="text-xs text-accent hover:underline font-mono"
            >
              Select All
            </button>
          </div>
          {loadingAlgos ? (
            <div className="flex items-center gap-2 text-muted-foreground text-sm">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </div>
          ) : (
            <div className="space-y-2">
              {(algos ?? []).map(algo => (
                <label
                  key={algo.name}
                  className="flex items-start gap-3 cursor-pointer group"
                >
                  <Checkbox
                    checked={selectedAlgos.has(algo.name)}
                    onCheckedChange={() => toggleAlgo(algo.name)}
                    className="mt-0.5"
                  />
                  <div>
                    <div className="text-sm font-mono text-foreground group-hover:text-accent transition-colors">
                      {algo.display_name}
                    </div>
                    <div className="text-xs text-muted-foreground mt-0.5 font-mono">
                      {algo.exec_tf} · {algo.description}
                    </div>
                  </div>
                </label>
              ))}
            </div>
          )}
        </div>

        <div className="h-px bg-card-border" />

        {/* Symbols */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <span className="font-mono text-xs text-muted-foreground uppercase tracking-wider">
              Symbols
            </span>
            <button
              onClick={selectAllSymbols}
              className="text-xs text-accent hover:underline font-mono"
            >
              Select All
            </button>
          </div>
          {loadingStocks ? (
            <div className="flex items-center gap-2 text-muted-foreground text-sm">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </div>
          ) : (
            <div className="space-y-2">
              {(stocks ?? []).map(stock => (
                <label
                  key={stock.symbol}
                  className="flex items-start gap-3 cursor-pointer group"
                >
                  <Checkbox
                    checked={selectedSymbols.has(stock.symbol)}
                    onCheckedChange={() => toggleSymbol(stock.symbol)}
                    className="mt-0.5"
                  />
                  <div>
                    <div className="text-sm font-mono text-foreground group-hover:text-accent transition-colors">
                      {stock.symbol}
                    </div>
                    <div className="text-xs text-muted-foreground mt-0.5 font-mono">
                      {stock.name} · spread {stock.spread_points}pts
                    </div>
                  </div>
                </label>
              ))}
            </div>
          )}
        </div>

        <div className="h-px bg-card-border" />

        {/* Date range */}
        <div>
          <div className="font-mono text-xs text-muted-foreground uppercase tracking-wider mb-3">
            Period (optional)
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="font-mono text-xs text-muted-foreground mb-1 block">Start Date</label>
              <input
                type="date"
                value={startDate}
                onChange={e => setStartDate(e.target.value)}
                className="w-full h-8 px-2 text-xs font-mono bg-secondary border border-card-border rounded text-foreground focus:outline-none focus:border-accent"
              />
            </div>
            <div>
              <label className="font-mono text-xs text-muted-foreground mb-1 block">End Date</label>
              <input
                type="date"
                value={endDate}
                onChange={e => setEndDate(e.target.value)}
                className="w-full h-8 px-2 text-xs font-mono bg-secondary border border-card-border rounded text-foreground focus:outline-none focus:border-accent"
              />
            </div>
          </div>
          {(startDate || endDate) && (
            <div className="mt-2 text-xs text-muted-foreground font-mono">
              Backtesting {startDate || '(start)'} → {endDate || '(end)'}
            </div>
          )}
        </div>

        {error && (
          <div className="text-sell text-sm font-mono bg-sell/10 border border-sell/20 rounded px-3 py-2">
            {error}
          </div>
        )}

        <Button
          onClick={handleRun}
          disabled={running || selectedAlgos.size === 0 || selectedSymbols.size === 0}
          className="w-full"
        >
          {running ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Starting…
            </>
          ) : (
            `Run Backtest (${selectedAlgos.size}×${selectedSymbols.size})`
          )}
        </Button>
      </div>
    </TerminalCard>
  )
}
