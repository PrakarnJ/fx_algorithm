import { useState, useEffect } from 'react'
import { useBacktestResults, useStocks } from '@/hooks/useApi'
import { RankingTable } from '@/components/dashboard/RankingTable'
import { RunConfigForm } from '@/components/backtest/RunConfigForm'
import { ProgressFeed } from '@/components/backtest/ProgressFeed'
import { TerminalCard } from '@/components/shared/TerminalCard'
import { ChartPlayer } from '@/components/replay/ChartPlayer'
import { TradeLogPanel } from '@/components/backtest/TradeLogPanel'
import { Button } from '@/components/ui/button'
import { apiFetch } from '@/lib/api'
import type { BacktestResult } from '@/lib/api'
import { Loader2, RefreshCw, ChevronDown, ChevronRight, X, RotateCcw, List, Play } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ReplayTarget {
  algo: string
  symbol: string
}

export function DashboardPage() {
  const { data: results, isLoading, error, mutate } = useBacktestResults()
  const { data: stocks } = useStocks()

  // ── Run backtest section ────────────────────────────────────────────
  const [runOpen, setRunOpen] = useState(false)
  const [jobId, setJobId] = useState<string | null>(null)
  const [runComplete, setRunComplete] = useState(false)

  function handleJobStarted(id: string) {
    setJobId(id)
    setRunOpen(true)
    setRunComplete(false)
  }

  function handleRunComplete() {
    setRunComplete(true)
    mutate() // refresh rankings with new results
  }

  function handleNewRun() {
    setJobId(null)
    setRunComplete(false)
  }

  // ── Replay panel ────────────────────────────────────────────────────
  const [replayTarget, setReplayTarget] = useState<ReplayTarget | null>(null)
  const [replaySessionId, setReplaySessionId] = useState<string | null>(null)
  const [replayLoading, setReplayLoading] = useState(false)
  const [replayError, setReplayError] = useState<string | null>(null)

  useEffect(() => {
    if (!replayTarget) { setReplaySessionId(null); return }
    let cancelled = false
    setReplaySessionId(null)
    setReplayLoading(true)
    setReplayError(null)
    apiFetch<{ session_id: string }>('/api/replay/start', {
      method: 'POST',
      body: JSON.stringify({ algo_name: replayTarget.algo, symbol: replayTarget.symbol }),
    })
      .then(res => { if (!cancelled) setReplaySessionId(res.session_id) })
      .catch(e => { if (!cancelled) setReplayError(e instanceof Error ? e.message : 'Failed') })
      .finally(() => { if (!cancelled) setReplayLoading(false) })
    return () => { cancelled = true }
  }, [replayTarget])

  // ── Trade log panel ─────────────────────────────────────────────────
  const [tradeLogTarget, setTradeLogTarget] = useState<BacktestResult | null>(null)
  // Which panel was opened last ('replay' | 'trades')
  const [lastPanel, setLastPanel] = useState<'replay' | 'trades'>('replay')

  function handleShowReplay(algo: string, symbol: string) {
    setReplayTarget({ algo, symbol })
    setLastPanel('replay')
  }

  function handleShowTrades(result: BacktestResult) {
    setTradeLogTarget(result)
    setLastPanel('trades')
  }

  function closePanel() {
    setReplayTarget(null)
    setTradeLogTarget(null)
  }

  const panelOpen = replayTarget !== null || tradeLogTarget !== null

  // Look up tick_size for the trade log symbol
  const tradeLogTickSize = tradeLogTarget
    ? (stocks?.find(s => s.symbol === tradeLogTarget.symbol)?.tick_size ?? 0.01)
    : 0.01

  // Panel header info
  const panelIsReplay = lastPanel === 'replay' && replayTarget !== null
  const panelIsTrades = lastPanel === 'trades' && tradeLogTarget !== null

  return (
    <div
      className={cn('flex', panelOpen && 'overflow-hidden')}
      style={panelOpen ? { height: '100vh' } : undefined}
    >
      {/* ── Left column ─────────────────────────────────────────────── */}
      <div
        className={cn(
          panelOpen ? 'w-[480px] flex-shrink-0 overflow-y-auto border-r border-card-border' : 'flex-1',
          'p-6 space-y-4',
        )}
      >
        {/* Page header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-foreground">Research Platform</h1>
            <p className="text-sm text-muted-foreground font-mono mt-0.5">
              Run backtests · review results · replay signals
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => mutate()} className="gap-1.5">
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>

        {/* ── Run Backtest collapsible ── */}
        <div className="rounded-md border border-card-border overflow-hidden">
          <div className="flex items-center">
            <button
              className="flex-1 flex items-center justify-between px-4 py-3 font-mono text-sm font-medium text-foreground hover:bg-secondary/20 transition-colors"
              onClick={() => setRunOpen(o => !o)}
            >
              <span className="flex items-center gap-2">
                {runOpen
                  ? <ChevronDown className="h-4 w-4 text-accent" />
                  : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                Run Backtest
              </span>
              {jobId && !runComplete && (
                <span className="flex items-center gap-1.5 text-xs text-accent">
                  <Loader2 className="h-3 w-3 animate-spin" /> running…
                </span>
              )}
              {runComplete && (
                <span className="text-xs text-buy font-mono">✓ complete</span>
              )}
            </button>
            {runComplete && (
              <button
                className="px-3 py-3 text-xs font-mono text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors border-l border-card-border"
                onClick={handleNewRun}
                title="New run"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                New Run
              </button>
            )}
          </div>

          {runOpen && (
            <div className="border-t border-card-border p-4 space-y-4 bg-secondary/5">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {!jobId && <RunConfigForm onJobStarted={handleJobStarted} />}
                {jobId ? (
                  <ProgressFeed jobId={jobId} onComplete={handleRunComplete} />
                ) : (
                  <TerminalCard title="Progress">
                    <div className="flex flex-col items-center justify-center py-10 text-muted-foreground font-mono text-sm">
                      <div className="text-3xl text-accent mb-3">_</div>
                      Configure and click Run Backtest.
                    </div>
                  </TerminalCard>
                )}
              </div>
            </div>
          )}
        </div>

        {/* ── Rankings ── */}
        <TerminalCard title="Strategy Rankings — sorted by Profit Factor">
          {isLoading ? (
            <div className="flex items-center justify-center py-16 gap-2 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
              <span className="font-mono text-sm">Loading…</span>
            </div>
          ) : error ? (
            <div className="text-sell font-mono text-sm py-8 text-center">
              Failed to load. Is the backend running?
              <br />
              <button onClick={() => mutate()} className="mt-2 text-accent hover:underline">Retry</button>
            </div>
          ) : (
            <RankingTable
              results={results ?? []}
              onReplay={handleShowReplay}
              onShowTrades={handleShowTrades}
            />
          )}
        </TerminalCard>
      </div>

      {/* ── Right panel: Replay or Trade Log ───────────────────────── */}
      {panelOpen && (
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Panel header */}
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-card-border flex-shrink-0 bg-background">
            <div className="flex items-center gap-3 font-mono text-xs">
              {panelIsReplay ? (
                <>
                  <Play className="h-3 w-3 text-accent" />
                  <span className="text-accent uppercase tracking-wider">Replay</span>
                  <span className="text-foreground font-semibold">{replayTarget?.algo}</span>
                  <span className="text-muted-foreground">·</span>
                  <span className="text-accent">{replayTarget?.symbol}</span>
                  {replayLoading && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
                  {replayError && <span className="text-sell">{replayError}</span>}
                </>
              ) : (
                <>
                  <List className="h-3 w-3 text-accent" />
                  <span className="text-accent uppercase tracking-wider">Trade Log</span>
                  <span className="text-foreground font-semibold">{tradeLogTarget?.algo}</span>
                  <span className="text-muted-foreground">·</span>
                  <span className="text-accent">{tradeLogTarget?.symbol}</span>
                </>
              )}
            </div>
            <div className="flex items-center gap-1">
              {/* Tab switcher when both targets are available */}
              {replayTarget && tradeLogTarget && (
                <>
                  <Button
                    size="sm"
                    variant={panelIsReplay ? 'outline' : 'ghost'}
                    className="h-6 px-2 text-xs"
                    onClick={() => setLastPanel('replay')}
                  >
                    <Play className="h-3 w-3 mr-1" />
                    Replay
                  </Button>
                  <Button
                    size="sm"
                    variant={panelIsTrades ? 'outline' : 'ghost'}
                    className="h-6 px-2 text-xs"
                    onClick={() => setLastPanel('trades')}
                  >
                    <List className="h-3 w-3 mr-1" />
                    Trades
                  </Button>
                </>
              )}
              <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={closePanel} title="Close">
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* Panel content */}
          <div className="flex-1 overflow-hidden">
            {panelIsReplay
              ? <ChartPlayer sessionId={replaySessionId} />
              : tradeLogTarget && (
                  <TradeLogPanel result={tradeLogTarget} tickSize={tradeLogTickSize} />
                )
            }
          </div>
        </div>
      )}
    </div>
  )
}
