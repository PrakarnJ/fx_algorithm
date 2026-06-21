import { useRef, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Play, Pause, SkipBack, SkipForward } from 'lucide-react'
import type { ReplayAction } from '@/hooks/useReplayWebSocket'

interface PlaybackControlsProps {
  isPlaying: boolean
  barIndex: number
  totalBars: number
  speed: number
  onAction: (action: ReplayAction) => void
}

const SPEEDS = [0.5, 1, 5, 10, 50]

export function PlaybackControls({
  isPlaying,
  barIndex,
  totalBars,
  speed,
  onAction,
}: PlaybackControlsProps) {
  const progressRef = useRef<HTMLDivElement>(null)

  const handleProgressClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!progressRef.current) return
    const rect = progressRef.current.getBoundingClientRect()
    const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
    const bar_index = Math.round(pct * (totalBars - 1))
    onAction({ action: 'seek', bar_index })
  }, [totalBars, onAction])

  const pct = totalBars > 0 ? (barIndex / (totalBars - 1)) * 100 : 0

  return (
    <div className="border-t border-card-border bg-background p-3">
      {/* Progress bar */}
      <div
        ref={progressRef}
        className="relative h-2 bg-secondary rounded-full cursor-pointer mb-3 group"
        onClick={handleProgressClick}
      >
        <div
          className="absolute top-0 left-0 h-full bg-accent rounded-full transition-all"
          style={{ width: `${pct}%` }}
        />
        {/* Scrubber handle */}
        <div
          className="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-accent rounded-full border-2 border-background shadow group-hover:scale-125 transition-transform"
          style={{ left: `calc(${pct}% - 6px)` }}
        />
      </div>

      {/* Controls row */}
      <div className="flex items-center gap-3">
        {/* Play / Pause */}
        <Button
          size="icon"
          variant="outline"
          className="h-8 w-8"
          onClick={() => onAction(isPlaying ? { action: 'pause' } : { action: 'play', speed })}
        >
          {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
        </Button>

        {/* Step back */}
        <Button
          size="icon"
          variant="outline"
          className="h-8 w-8"
          onClick={() => onAction({ action: 'step_back' })}
          disabled={barIndex === 0}
        >
          <SkipBack className="h-4 w-4" />
        </Button>

        {/* Step forward */}
        <Button
          size="icon"
          variant="outline"
          className="h-8 w-8"
          onClick={() => onAction({ action: 'step' })}
          disabled={barIndex >= totalBars - 1}
        >
          <SkipForward className="h-4 w-4" />
        </Button>

        {/* Speed selector */}
        <div className="flex items-center gap-1">
          {SPEEDS.map(s => (
            <button
              key={s}
              onClick={() => onAction({ action: 'speed', speed: s })}
              className={`px-2 py-0.5 rounded text-xs font-mono transition-colors ${
                speed === s
                  ? 'bg-accent text-background'
                  : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
              }`}
            >
              {s}x
            </button>
          ))}
        </div>

        {/* Bar counter */}
        <div className="ml-auto font-mono text-xs text-muted-foreground">
          <span className="text-foreground">{barIndex}</span>
          <span className="mx-1">/</span>
          <span>{totalBars}</span>
        </div>
      </div>
    </div>
  )
}
