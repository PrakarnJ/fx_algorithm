import { Badge } from '@/components/ui/badge'

interface MetricBadgeProps {
  value: number
  type: 'pf' | 'wr' | 'dd' | 'sharpe'
}

export function MetricBadge({ value, type }: MetricBadgeProps) {
  if (type === 'pf') {
    const variant = value >= 1.5 ? 'success' : value >= 1.0 ? 'warning' : 'danger'
    return <Badge variant={variant}>{value.toFixed(2)}</Badge>
  }
  if (type === 'wr') {
    const variant = value >= 55 ? 'success' : value >= 45 ? 'warning' : 'danger'
    return <Badge variant={variant}>{value.toFixed(1)}%</Badge>
  }
  if (type === 'dd') {
    const variant = value > -200 ? 'success' : value > -500 ? 'warning' : 'danger'
    return (
      <Badge variant={variant} className="font-mono">
        {value.toFixed(0)}
      </Badge>
    )
  }
  if (type === 'sharpe') {
    const variant = value >= 1 ? 'success' : value >= 0 ? 'warning' : 'danger'
    return <Badge variant={variant}>{value.toFixed(2)}</Badge>
  }
  return <Badge>{String(value)}</Badge>
}
