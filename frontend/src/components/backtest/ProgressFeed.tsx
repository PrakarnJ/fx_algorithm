import { useEffect, useRef, useState } from 'react'
import { Progress } from '@/components/ui/progress'
import { TerminalCard } from '@/components/shared/TerminalCard'
import { MetricBadge } from '@/components/dashboard/MetricBadge'
import { WS_BASE, type BacktestResult } from '@/lib/api'
import { CheckCircle2, XCircle, Loader2 } from 'lucide-react'

interface ProgressEntry {
  key: string
  algo: string
  symbol: string
  status: 'running' | 'done' | 'error'
  result?: BacktestResult
  error?: string
}

interface ProgressFeedProps {
  jobId: string
  onComplete?: (results: BacktestResult[]) => void
}

interface ProgressMessage {
  type: 'progress'
  done: number
  total: number
  result?: BacktestResult & { error?: string }
}

interface DoneMessage {
  type: 'done'
}

type WsMessage = ProgressMessage | DoneMessage

export function ProgressFeed({ jobId, onComplete }: ProgressFeedProps) {
  const wsRef = useRef<WebSocket | null>(null)
  const collectedRef = useRef<BacktestResult[]>([])
  const [entries, setEntries] = useState<ProgressEntry[]>([])
  const [done, setDone] = useState(0)
  const [total, setTotal] = useState(1)
  const [completed, setCompleted] = useState(false)

  useEffect(() => {
    collectedRef.current = []
    const ws = new WebSocket(`${WS_BASE}/ws/backtest/${jobId}`)
    wsRef.current = ws

    ws.onmessage = (ev: MessageEvent) => {
      try {
        const msg = JSON.parse(ev.data as string) as WsMessage
        if (msg.type === 'progress') {
          setDone(msg.done)
          setTotal(msg.total)
          if (msg.result) {
            const r = msg.result
            const key = `${r.algo}_${r.symbol}`
            if (!r.error) collectedRef.current = [...collectedRef.current, r]
            setEntries(prev => {
              const filtered = prev.filter(e => e.key !== key)
              return [
                ...filtered,
                {
                  key,
                  algo: r.algo,
                  symbol: r.symbol,
                  status: r.error ? 'error' : 'done',
                  result: r.error ? undefined : r,
                  error: r.error ?? undefined,
                },
              ]
            })
          }
        } else if (msg.type === 'done') {
          setCompleted(true)
          ws.close()
          onComplete?.(collectedRef.current)
        }
      } catch {
        // ignore
      }
    }

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [jobId])

  const pct = total > 0 ? (done / total) * 100 : 0

  return (
    <TerminalCard title="Progress">
      <div className="space-y-4">
        {/* Progress bar */}
        <div>
          <div className="flex justify-between text-xs font-mono text-muted-foreground mb-2">
            <span>{completed ? 'Complete' : 'Running…'}</span>
            <span>{done}/{total}</span>
          </div>
          <Progress value={pct} />
        </div>

        {/* Entry list */}
        <div className="space-y-2 max-h-96 overflow-y-auto">
          {entries.map(entry => (
            <div
              key={entry.key}
              className="flex items-start gap-3 p-2 rounded border border-card-border/50 bg-secondary/10"
            >
              <div className="mt-0.5 flex-shrink-0">
                {entry.status === 'running' && (
                  <Loader2 className="h-4 w-4 animate-spin text-accent" />
                )}
                {entry.status === 'done' && (
                  <CheckCircle2 className="h-4 w-4 text-buy" />
                )}
                {entry.status === 'error' && (
                  <XCircle className="h-4 w-4 text-sell" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-xs text-foreground">{entry.algo}</span>
                  <span className="font-mono text-xs text-accent">{entry.symbol}</span>
                  {entry.status === 'done' && entry.result?.metrics && (
                    <>
                      <MetricBadge value={entry.result.metrics.profit_factor} type="pf" />
                      <span className="font-mono text-xs text-muted-foreground">
                        {entry.result.metrics.trade_count} trades
                      </span>
                    </>
                  )}
                </div>
                {entry.status === 'error' && (
                  <div className="text-xs text-sell font-mono mt-0.5 truncate">
                    {entry.error}
                  </div>
                )}
              </div>
            </div>
          ))}
          {entries.length === 0 && !completed && (
            <div className="text-muted-foreground text-sm font-mono text-center py-4">
              Waiting for results…
            </div>
          )}
        </div>
      </div>
    </TerminalCard>
  )
}
