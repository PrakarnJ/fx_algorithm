import { useState, useCallback, useEffect, useRef } from 'react'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { CandlestickChart } from './CandlestickChart'
import { StochRsiChart } from './StochRsiChart'
import { PlaybackControls } from './PlaybackControls'
import { ThinkingPanel } from './ThinkingPanel'
import { useReplayWebSocket, type ReplayAction } from '@/hooks/useReplayWebSocket'
import type { ReplayFrame } from '@/lib/api'

export interface SessionSummary {
  totalPts: number
  wins: number
  losses: number
}

interface ChartPlayerProps {
  sessionId: string | null
}

export function ChartPlayer({ sessionId }: ChartPlayerProps) {
  const [frame, setFrame] = useState<ReplayFrame | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [barIndex, setBarIndex] = useState(0)
  const [totalBars, setTotalBars] = useState(0)
  const [summary, setSummary] = useState<SessionSummary>({ totalPts: 0, wins: 0, losses: 0 })
  const [sessionEnded, setSessionEnded] = useState(false)

  const countedTradesRef = useRef<Set<number>>(new Set())

  const handleFrame = useCallback((f: ReplayFrame) => {
    setFrame(f)
    setBarIndex(f.bar_index)
    setTotalBars(f.total_bars)
    if (f.trade_closed && !countedTradesRef.current.has(f.bar_index)) {
      countedTradesRef.current.add(f.bar_index)
      const pts = f.trade_closed.profit_pips ?? 0
      setSummary(prev => ({
        totalPts: prev.totalPts + pts,
        wins: prev.wins + (pts > 0 ? 1 : 0),
        losses: prev.losses + (pts <= 0 ? 1 : 0),
      }))
    }
  }, [])

  const handleDone = useCallback(() => {
    setIsPlaying(false)
    setSessionEnded(true)
  }, [])

  // Reset all state whenever a new session is loaded
  useEffect(() => {
    setFrame(null)
    setIsPlaying(false)
    setBarIndex(0)
    setTotalBars(0)
    setSummary({ totalPts: 0, wins: 0, losses: 0 })
    setSessionEnded(false)
    countedTradesRef.current = new Set()
  }, [sessionId])

  const { send, status } = useReplayWebSocket({
    sessionId,
    onFrame: handleFrame,
    onDone: handleDone,
  })

  // Auto-play as soon as the WebSocket connects
  useEffect(() => {
    if (status === 'open') {
      send({ action: 'play', speed: 1 })
      setIsPlaying(true)
    }
  }, [status, send])

  function handleAction(action: ReplayAction) {
    if (action.action === 'play') setIsPlaying(true)
    if (action.action === 'pause') setIsPlaying(false)
    if (action.action === 'speed') setSpeed(action.speed)
    send(action)
  }

  // "Connection lost" only for genuine errors, not normal session completion
  const showLostOverlay = sessionId && (status === 'error' || (status === 'closed' && !sessionEnded))

  return (
    <div className="flex flex-col h-full relative">
      {/* Connecting spinner */}
      {sessionId && status === 'connecting' && !frame && (
        <div className="absolute inset-0 flex items-center justify-center z-10 bg-background/60">
          <Loader2 className="h-8 w-8 animate-spin text-accent" />
        </div>
      )}

      {/* Connection lost — genuine error only (not normal session end) */}
      {showLostOverlay && (
        <div className="absolute inset-0 bg-background/80 flex items-center justify-center z-10">
          <div className="text-center font-mono space-y-3">
            <div className="text-sell text-sm">⚠ Connection lost</div>
            <Button size="sm" variant="outline" onClick={() => window.location.reload()}>
              Reload page
            </Button>
          </div>
        </div>
      )}

      {/* Replay complete badge — non-blocking, allows timeline seeks */}
      {sessionEnded && !showLostOverlay && (
        <div className="absolute top-2 right-2 z-10 px-2 py-1 rounded bg-secondary/80 border border-card-border font-mono text-xs text-muted-foreground">
          Replay complete — click timeline to review
        </div>
      )}

      {/* Chart + Thinking panel */}
      <div className="flex flex-1 overflow-hidden" style={{ minHeight: 0 }}>
        {/* Left: main candlestick chart (top) + StochRSI mini-chart (bottom) */}
        <div className="flex-[7] flex flex-col border-r border-card-border" style={{ minWidth: 0 }}>
          <div className="flex-[4]" style={{ minHeight: 0 }}>
            <CandlestickChart key={sessionId ?? ''} frame={frame} containerClassName="w-full h-full" />
          </div>
          <div className="flex-[1] border-t border-card-border" style={{ minHeight: 0 }}>
            <StochRsiChart key={sessionId ?? ''} frame={frame} containerClassName="w-full h-full" />
          </div>
        </div>
        <div className="flex-[3] overflow-hidden" style={{ minWidth: 0 }}>
          <ThinkingPanel frame={frame} summary={summary} />
        </div>
      </div>

      {/* Playback controls — always visible and clickable */}
      <PlaybackControls
        isPlaying={isPlaying}
        barIndex={barIndex}
        totalBars={totalBars}
        speed={speed}
        onAction={handleAction}
      />
    </div>
  )
}
