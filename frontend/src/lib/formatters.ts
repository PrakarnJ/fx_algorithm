export function formatPF(value: number | undefined | null): string {
  if (value == null || isNaN(value)) return '—'
  return value.toFixed(2)
}

export function formatPct(value: number | undefined | null): string {
  if (value == null || isNaN(value)) return '—'
  return `${value.toFixed(1)}%`
}

export function formatPts(value: number | undefined | null): string {
  if (value == null || isNaN(value)) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}`
}

export function formatR(value: number | undefined | null): string {
  if (value == null || isNaN(value)) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}R`
}

export function formatSharpe(value: number | undefined | null): string {
  if (value == null || isNaN(value)) return '—'
  return value.toFixed(2)
}

export function formatDateTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString('en-US', {
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
  } catch {
    return iso
  }
}

export function formatPrice(value: number): string {
  return value.toFixed(2)
}
