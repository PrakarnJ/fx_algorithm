import { Settings, X } from 'lucide-react'
import { Button } from '@/components/ui/button'

export interface IndicatorSettings {
  emaFast: { enabled: boolean; period: number }
  emaSlow: { enabled: boolean; period: number }
  bb: { enabled: boolean; period: number; mult: number }
  oscillator: 'rsi' | 'atr' | 'adx' | null
  rsiPeriod: number
  atrPeriod: number
  adxPeriod: number
}

export const DEFAULT_INDICATORS: IndicatorSettings = {
  emaFast: { enabled: false, period: 9 },
  emaSlow: { enabled: false, period: 21 },
  bb: { enabled: false, period: 20, mult: 2 },
  oscillator: null,
  rsiPeriod: 14,
  atrPeriod: 14,
  adxPeriod: 14,
}

interface Props {
  value: IndicatorSettings
  onChange: (v: IndicatorSettings) => void
  onClose: () => void
}

function NumInput({
  value,
  onChange,
  min = 1,
  max = 200,
}: {
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
}) {
  return (
    <input
      type="number"
      value={value}
      min={min}
      max={max}
      onChange={e => onChange(Math.max(min, Math.min(max, parseInt(e.target.value) || min)))}
      className="w-16 h-6 px-2 text-xs font-mono bg-secondary border border-card-border rounded text-foreground focus:outline-none focus:border-accent"
    />
  )
}

function Row({
  label,
  enabled,
  onToggle,
  children,
}: {
  label: string
  enabled: boolean
  onToggle: () => void
  children?: React.ReactNode
}) {
  return (
    <div className="flex items-center gap-3 py-2 border-b border-card-border/40">
      <button
        onClick={onToggle}
        className={`w-8 h-4 rounded-full transition-colors flex-shrink-0 relative ${
          enabled ? 'bg-accent' : 'bg-secondary'
        }`}
      >
        <span className={`absolute top-0.5 w-3 h-3 bg-white rounded-full transition-all ${
          enabled ? 'left-4' : 'left-0.5'
        }`} />
      </button>
      <span className="font-mono text-xs text-foreground w-28 flex-shrink-0">{label}</span>
      {enabled && children}
    </div>
  )
}

export function IndicatorConfig({ value, onChange, onClose }: Props) {
  const set = (patch: Partial<IndicatorSettings>) => onChange({ ...value, ...patch })

  return (
    <div className="absolute right-0 top-0 h-full w-64 bg-background border-l border-card-border z-20 flex flex-col shadow-xl">
      <div className="flex items-center justify-between px-4 py-3 border-b border-card-border">
        <div className="flex items-center gap-2 font-mono text-xs text-accent uppercase tracking-wider">
          <Settings className="h-3.5 w-3.5" />
          Indicators
        </div>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-1">
        <div className="font-mono text-xs text-muted-foreground uppercase tracking-wider mb-2">
          Overlays (price chart)
        </div>

        <Row
          label="EMA Fast"
          enabled={value.emaFast.enabled}
          onToggle={() => set({ emaFast: { ...value.emaFast, enabled: !value.emaFast.enabled } })}
        >
          <NumInput
            value={value.emaFast.period}
            onChange={p => set({ emaFast: { ...value.emaFast, period: p } })}
          />
        </Row>

        <Row
          label="EMA Slow"
          enabled={value.emaSlow.enabled}
          onToggle={() => set({ emaSlow: { ...value.emaSlow, enabled: !value.emaSlow.enabled } })}
        >
          <NumInput
            value={value.emaSlow.period}
            onChange={p => set({ emaSlow: { ...value.emaSlow, period: p } })}
          />
        </Row>

        <Row
          label="Bollinger Bands"
          enabled={value.bb.enabled}
          onToggle={() => set({ bb: { ...value.bb, enabled: !value.bb.enabled } })}
        >
          <NumInput
            value={value.bb.period}
            onChange={p => set({ bb: { ...value.bb, period: p } })}
          />
          <NumInput
            value={value.bb.mult}
            onChange={m => set({ bb: { ...value.bb, mult: m } })}
            min={1}
            max={5}
          />
        </Row>

        <div className="font-mono text-xs text-muted-foreground uppercase tracking-wider mt-4 mb-2">
          Oscillator (sub-pane)
        </div>

        {(
          [
            { key: 'rsi', label: 'RSI', periodKey: 'rsiPeriod' },
            { key: 'atr', label: 'ATR', periodKey: 'atrPeriod' },
            { key: 'adx', label: 'ADX', periodKey: 'adxPeriod' },
          ] as const
        ).map(({ key, label, periodKey }) => (
          <Row
            key={key}
            label={label}
            enabled={value.oscillator === key}
            onToggle={() => set({ oscillator: value.oscillator === key ? null : key })}
          >
            <NumInput
              value={value[periodKey]}
              onChange={p => set({ [periodKey]: p } as Partial<IndicatorSettings>)}
            />
          </Row>
        ))}
      </div>

      <div className="px-4 py-3 border-t border-card-border">
        <Button
          size="sm"
          variant="outline"
          className="w-full text-xs"
          onClick={() => onChange(DEFAULT_INDICATORS)}
        >
          Reset all
        </Button>
      </div>
    </div>
  )
}
