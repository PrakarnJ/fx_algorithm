import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ChartPlayer } from '@/components/replay/ChartPlayer'
import { useAlgorithms, useStocks } from '@/hooks/useApi'
import { apiFetch } from '@/lib/api'
import { Loader2 } from 'lucide-react'

export function ReplayPage() {
  const [searchParams] = useSearchParams()
  const { data: algos } = useAlgorithms()
  const { data: stocks } = useStocks()

  const algoParam = searchParams.get('algo')
  const symbolParam = searchParams.get('symbol')

  const [selectedAlgo, setSelectedAlgo] = useState(algoParam ?? '')
  const [selectedSymbol, setSelectedSymbol] = useState(symbolParam ?? '')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function doLoad(algo: string, symbol: string, start: string, end: string) {
    if (!algo || !symbol) {
      setError('Select an algorithm and symbol.')
      return
    }
    setError(null)
    setLoading(true)
    setSessionId(null)
    try {
      const res = await apiFetch<{ session_id: string; total_bars: number; exec_tf: string }>(
        '/api/replay/start',
        {
          method: 'POST',
          body: JSON.stringify({
            algo_name: algo,
            symbol,
            start_date: start || null,
            end_date: end || null,
          }),
        },
      )
      setSessionId(res.session_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start replay')
    } finally {
      setLoading(false)
    }
  }

  async function handleLoad() {
    doLoad(selectedAlgo, selectedSymbol, startDate, endDate)
  }

  // Auto-load (and re-load) whenever the algo+symbol URL params change —
  // covers both fresh mount and navigating from Dashboard while already on this page.
  useEffect(() => {
    if (algoParam && symbolParam) {
      setSelectedAlgo(algoParam)
      setSelectedSymbol(symbolParam)
      doLoad(algoParam, symbolParam, '', '')
    }
  }, [algoParam, symbolParam]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex flex-col h-screen">
      {/* Top bar */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-card-border bg-background flex-shrink-0">
        <span className="font-mono text-xs text-accent uppercase tracking-wider mr-2">
          Replay
        </span>

        <Select value={selectedAlgo} onValueChange={setSelectedAlgo}>
          <SelectTrigger className="w-48 h-8 text-xs">
            <SelectValue placeholder="Algorithm…" />
          </SelectTrigger>
          <SelectContent>
            {(algos ?? []).map(a => (
              <SelectItem key={a.name} value={a.name} className="text-xs">
                {a.display_name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={selectedSymbol} onValueChange={setSelectedSymbol}>
          <SelectTrigger className="w-32 h-8 text-xs">
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

        <div className="flex items-center gap-1 ml-1">
          <span className="text-xs text-muted-foreground font-mono">From</span>
          <input
            type="date"
            value={startDate}
            onChange={e => setStartDate(e.target.value)}
            className="h-8 px-2 text-xs font-mono bg-secondary border border-card-border rounded text-foreground focus:outline-none focus:border-accent"
          />
          <span className="text-xs text-muted-foreground font-mono">To</span>
          <input
            type="date"
            value={endDate}
            onChange={e => setEndDate(e.target.value)}
            className="h-8 px-2 text-xs font-mono bg-secondary border border-card-border rounded text-foreground focus:outline-none focus:border-accent"
          />
        </div>

        <Button
          size="sm"
          className="h-8 text-xs"
          onClick={handleLoad}
          disabled={loading || !selectedAlgo || !selectedSymbol}
        >
          {loading ? (
            <>
              <Loader2 className="mr-1.5 h-3 w-3 animate-spin" /> Loading…
            </>
          ) : (
            'Load'
          )}
        </Button>

        {error && (
          <span className="text-xs text-sell font-mono">{error}</span>
        )}
      </div>

      {/* Chart area */}
      <div className="flex-1 overflow-hidden">
        {sessionId ? (
          <ChartPlayer sessionId={sessionId} />
        ) : (
          <div className="h-full flex items-center justify-center text-muted-foreground font-mono text-sm">
            <div className="text-center">
              <div className="text-4xl text-accent mb-3">_</div>
              Select an algorithm and symbol, then click Load.
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
