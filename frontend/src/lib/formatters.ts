// XAUUSD contract math: 1 standard lot = 100 oz; engine qty is in oz.
// 0.01 lot = 1 oz → $0.10 P/L per pip ($0.10 price move).
export const OZ_PER_LOT = 100

export function fmtLots(qtyOz: number): string {
  return (qtyOz / OZ_PER_LOT).toFixed(2)
}

export function fmtUsd(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return '—'
  const sign = v < 0 ? '-' : ''
  return `${sign}$${Math.abs(v).toFixed(digits)}`
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
