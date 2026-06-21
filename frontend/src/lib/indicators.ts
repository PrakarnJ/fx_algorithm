// Client-side technical indicator computation.
// Formulas mirror indicators.py: Wilder's smoothing for RSI/ATR/ADX, standard EWM for EMA.

export function ema(closes: number[], period: number): (number | null)[] {
  const k = 2 / (period + 1)
  const out: (number | null)[] = new Array(closes.length).fill(null)
  let current: number | null = null
  for (let i = 0; i < closes.length; i++) {
    if (current === null) {
      if (i >= period - 1) {
        // Seed with simple average of first `period` values
        let sum = 0
        for (let j = i - period + 1; j <= i; j++) sum += closes[j]
        current = sum / period
        out[i] = current
      }
    } else {
      current = closes[i] * k + current * (1 - k)
      out[i] = current
    }
  }
  return out
}

export function rsi(closes: number[], period: number): (number | null)[] {
  const out: (number | null)[] = new Array(closes.length).fill(null)
  if (closes.length < period + 1) return out

  // Wilder's smoothing (alpha = 1/period)
  const alpha = 1 / period
  let avgGain = 0
  let avgLoss = 0

  // Seed: average of first `period` moves
  for (let i = 1; i <= period; i++) {
    const diff = closes[i] - closes[i - 1]
    if (diff > 0) avgGain += diff
    else avgLoss += -diff
  }
  avgGain /= period
  avgLoss /= period

  out[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss)

  for (let i = period + 1; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1]
    const gain = diff > 0 ? diff : 0
    const loss = diff < 0 ? -diff : 0
    avgGain = avgGain * (1 - alpha) + gain * alpha
    avgLoss = avgLoss * (1 - alpha) + loss * alpha
    out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss)
  }
  return out
}

export function atr(
  highs: number[],
  lows: number[],
  closes: number[],
  period: number,
): (number | null)[] {
  const out: (number | null)[] = new Array(closes.length).fill(null)
  const alpha = 1 / period

  // True range
  const tr: number[] = [highs[0] - lows[0]]
  for (let i = 1; i < closes.length; i++) {
    const hl = highs[i] - lows[i]
    const hc = Math.abs(highs[i] - closes[i - 1])
    const lc = Math.abs(lows[i] - closes[i - 1])
    tr.push(Math.max(hl, hc, lc))
  }

  if (tr.length < period) return out

  // Seed ATR with SMA of first `period` true ranges
  let current = 0
  for (let i = 0; i < period; i++) current += tr[i]
  current /= period
  out[period - 1] = current

  for (let i = period; i < tr.length; i++) {
    current = current * (1 - alpha) + tr[i] * alpha
    out[i] = current
  }
  return out
}

export function bollingerBands(
  closes: number[],
  period: number,
  mult: number,
): { upper: (number | null)[]; middle: (number | null)[]; lower: (number | null)[] } {
  const upper: (number | null)[] = new Array(closes.length).fill(null)
  const middle: (number | null)[] = new Array(closes.length).fill(null)
  const lower: (number | null)[] = new Array(closes.length).fill(null)

  for (let i = period - 1; i < closes.length; i++) {
    const slice = closes.slice(i - period + 1, i + 1)
    const mean = slice.reduce((a, b) => a + b, 0) / period
    const variance = slice.reduce((a, b) => a + (b - mean) ** 2, 0) / period
    const std = Math.sqrt(variance)
    middle[i] = mean
    upper[i] = mean + mult * std
    lower[i] = mean - mult * std
  }
  return { upper, middle, lower }
}

export function adx(
  highs: number[],
  lows: number[],
  closes: number[],
  period: number,
): (number | null)[] {
  const out: (number | null)[] = new Array(closes.length).fill(null)
  const alpha = 1 / period
  const n = closes.length
  if (n < period + 1) return out

  const plusDM: number[] = [0]
  const minusDM: number[] = [0]
  const trArr: number[] = [highs[0] - lows[0]]

  for (let i = 1; i < n; i++) {
    const upMove = highs[i] - highs[i - 1]
    const downMove = lows[i - 1] - lows[i]
    plusDM.push(upMove > downMove && upMove > 0 ? upMove : 0)
    minusDM.push(downMove > upMove && downMove > 0 ? downMove : 0)
    const hl = highs[i] - lows[i]
    const hc = Math.abs(highs[i] - closes[i - 1])
    const lc = Math.abs(lows[i] - closes[i - 1])
    trArr.push(Math.max(hl, hc, lc))
  }

  // Seed smoothed values
  let smoothTR = trArr.slice(1, period + 1).reduce((a, b) => a + b, 0)
  let smoothPlus = plusDM.slice(1, period + 1).reduce((a, b) => a + b, 0)
  let smoothMinus = minusDM.slice(1, period + 1).reduce((a, b) => a + b, 0)

  const dxArr: number[] = []

  function calcDX() {
    const pDI = smoothTR === 0 ? 0 : 100 * smoothPlus / smoothTR
    const mDI = smoothTR === 0 ? 0 : 100 * smoothMinus / smoothTR
    const sum = pDI + mDI
    return sum === 0 ? 0 : 100 * Math.abs(pDI - mDI) / sum
  }

  dxArr.push(calcDX())

  for (let i = period + 1; i < n; i++) {
    smoothTR = smoothTR * (1 - alpha) + trArr[i] * alpha
    smoothPlus = smoothPlus * (1 - alpha) + plusDM[i] * alpha
    smoothMinus = smoothMinus * (1 - alpha) + minusDM[i] * alpha
    dxArr.push(calcDX())
  }

  // ADX = EMA of DX over `period` bars
  if (dxArr.length < period) return out

  let adxVal = dxArr.slice(0, period).reduce((a, b) => a + b, 0) / period
  out[2 * period] = adxVal

  for (let i = period; i < dxArr.length; i++) {
    adxVal = adxVal * (1 - alpha) + dxArr[i] * alpha
    out[period + 1 + i] = adxVal
  }
  return out
}
