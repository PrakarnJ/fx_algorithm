import { useEffect, useRef } from 'react'
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type LineData,
  type IPriceLine,
  type SeriesMarker,
  LineStyle,
  CrosshairMode,
  type Time,
} from 'lightweight-charts'
import type { ReplayFrame } from '@/lib/api'

interface CandlestickChartProps {
  frame: ReplayFrame | null
  containerClassName?: string
}

function buildLineData(
  valueArr: Array<number | undefined>,
  barsArr: Array<CandlestickData | undefined>,
  upTo: number,
): LineData[] {
  const out: LineData[] = []
  for (let i = 0; i <= upTo; i++) {
    const v = valueArr[i]
    const b = barsArr[i]
    if (v !== undefined && b !== undefined) out.push({ time: b.time, value: v })
  }
  return out
}

export function CandlestickChart({ frame, containerClassName }: CandlestickChartProps) {
  const containerRef  = useRef<HTMLDivElement>(null)
  const chartRef      = useRef<IChartApi | null>(null)
  const seriesRef     = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const slLineRef     = useRef<IPriceLine | null>(null)
  const tpLineRef     = useRef<IPriceLine | null>(null)

  // EMA line series
  const ema9Ref  = useRef<ISeriesApi<'Line'> | null>(null)
  const ema21Ref = useRef<ISeriesApi<'Line'> | null>(null)
  const ema34Ref = useRef<ISeriesApi<'Line'> | null>(null)
  const ema89Ref = useRef<ISeriesApi<'Line'> | null>(null)

  // S/R price lines (cleared & redrawn each frame)
  const srLinesRef = useRef<IPriceLine[]>([])

  // Accumulated bar + EMA data for backward-seek rebuilds
  const barsArr   = useRef<Array<CandlestickData | undefined>>([])
  const ema9Arr   = useRef<Array<number | undefined>>([])
  const ema21Arr  = useRef<Array<number | undefined>>([])
  const ema34Arr  = useRef<Array<number | undefined>>([])
  const ema89Arr  = useRef<Array<number | undefined>>([])
  const markersMap = useRef<Map<number, SeriesMarker<Time>>>(new Map())
  const drawnThroughRef = useRef<number>(-1)

  // Create chart + all series once on mount
  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: { background: { color: '#0d1117' }, textColor: '#8b949e' },
      grid: {
        vertLines: { color: '#1a2332' },
        horzLines: { color: '#1a2332' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#1a2332' },
      timeScale: { borderColor: '#1a2332', timeVisible: true, secondsVisible: false },
    })

    const candles = chart.addCandlestickSeries({
      upColor: '#22c55e', downColor: '#ef4444',
      borderUpColor: '#22c55e', borderDownColor: '#ef4444',
      wickUpColor: '#22c55e', wickDownColor: '#ef4444',
    })

    // EMA lines — trigger pair (fast, thin) and trend pair (slow, thick)
    const e9  = chart.addLineSeries({ color: '#ffffff', lineWidth: 1, priceLineVisible: false, crosshairMarkerVisible: false, lastValueVisible: false })
    const e21 = chart.addLineSeries({ color: '#f472b6', lineWidth: 1, priceLineVisible: false, crosshairMarkerVisible: false, lastValueVisible: false })
    const e34 = chart.addLineSeries({ color: '#facc15', lineWidth: 2, priceLineVisible: false, crosshairMarkerVisible: false, lastValueVisible: false })
    const e89 = chart.addLineSeries({ color: '#3b82f6', lineWidth: 2, priceLineVisible: false, crosshairMarkerVisible: false, lastValueVisible: false })

    chartRef.current  = chart
    seriesRef.current = candles
    ema9Ref.current   = e9
    ema21Ref.current  = e21
    ema34Ref.current  = e34
    ema89Ref.current  = e89

    return () => {
      chart.remove()
      chartRef.current = seriesRef.current = null
      ema9Ref.current = ema21Ref.current = ema34Ref.current = ema89Ref.current = null
    }
  }, [])

  // Update on each new frame
  useEffect(() => {
    if (!frame || !seriesRef.current) return

    const series = seriesRef.current
    const bi = frame.bar_index
    const timeSeconds = Math.floor(new Date(frame.bar_time).getTime() / 1000) as Time

    // Candlestick bar
    const bar: CandlestickData = {
      time: timeSeconds,
      open: frame.bar.open, high: frame.bar.high,
      low: frame.bar.low, close: frame.bar.close,
    }
    barsArr.current[bi] = bar

    // EMA values from indicator snapshot
    const snap = frame.indicator_snapshot
    const e9v  = typeof snap.ema9_m15  === 'number' ? snap.ema9_m15  : undefined
    const e21v = typeof snap.ema21_m15 === 'number' ? snap.ema21_m15 : undefined
    const e34v = typeof snap.ema34_m15 === 'number' ? snap.ema34_m15 : undefined
    const e89v = typeof snap.ema89_m15 === 'number' ? snap.ema89_m15 : undefined
    if (e9v  !== undefined) ema9Arr.current[bi]  = e9v
    if (e21v !== undefined) ema21Arr.current[bi] = e21v
    if (e34v !== undefined) ema34Arr.current[bi] = e34v
    if (e89v !== undefined) ema89Arr.current[bi] = e89v

    // Signal marker
    if (frame.signal) {
      const isBuy = frame.signal.direction === 'buy'
      markersMap.current.set(bi, {
        time: timeSeconds,
        position: isBuy ? 'belowBar' : 'aboveBar',
        color: isBuy ? '#22c55e' : '#ef4444',
        shape: isBuy ? 'arrowUp' : 'arrowDown',
        text: isBuy ? 'BUY' : 'SELL',
      })
    }

    const isSeeking = bi <= drawnThroughRef.current

    if (isSeeking) {
      // Backward seek — rebuild all series up to bi
      const dataSlice = (barsArr.current.slice(0, bi + 1) as Array<CandlestickData | undefined>)
        .filter((b): b is CandlestickData => b !== undefined)
      try { series.setData(dataSlice) } catch { /* ignore */ }
      drawnThroughRef.current = bi

      const relevantMarkers = [...markersMap.current.entries()]
        .filter(([idx]) => idx <= bi)
        .sort(([a], [b]) => a - b)
        .map(([, m]) => m)
      series.setMarkers(relevantMarkers)

      // Rebuild EMA series
      ema9Ref.current?.setData(buildLineData(ema9Arr.current,  barsArr.current, bi))
      ema21Ref.current?.setData(buildLineData(ema21Arr.current, barsArr.current, bi))
      ema34Ref.current?.setData(buildLineData(ema34Arr.current, barsArr.current, bi))
      ema89Ref.current?.setData(buildLineData(ema89Arr.current, barsArr.current, bi))
    } else {
      // Forward — incremental updates
      try { series.update(bar) } catch { /* ignore */ }
      drawnThroughRef.current = bi
      chartRef.current?.timeScale().scrollToPosition(0, false)

      if (frame.signal) {
        const markers = [...markersMap.current.entries()]
          .sort(([a], [b]) => a - b)
          .map(([, m]) => m)
        series.setMarkers(markers)
      }

      if (e9v  !== undefined) ema9Ref.current?.update({ time: timeSeconds, value: e9v })
      if (e21v !== undefined) ema21Ref.current?.update({ time: timeSeconds, value: e21v })
      if (e34v !== undefined) ema34Ref.current?.update({ time: timeSeconds, value: e34v })
      if (e89v !== undefined) ema89Ref.current?.update({ time: timeSeconds, value: e89v })
    }

    // SL / TP trade lines
    if (slLineRef.current) { series.removePriceLine(slLineRef.current); slLineRef.current = null }
    if (tpLineRef.current) { series.removePriceLine(tpLineRef.current); tpLineRef.current = null }
    if (frame.open_trade) {
      slLineRef.current = series.createPriceLine({
        price: frame.open_trade.sl, color: '#ef4444',
        lineWidth: 1, lineStyle: LineStyle.Dashed,
        axisLabelVisible: true, title: 'SL',
      })
      tpLineRef.current = series.createPriceLine({
        price: frame.open_trade.tp, color: '#22c55e',
        lineWidth: 1, lineStyle: LineStyle.Dashed,
        axisLabelVisible: true, title: 'TP',
      })
    }

    // S/R horizontal levels — redraw from current snapshot
    srLinesRef.current.forEach(l => { try { series.removePriceLine(l) } catch { /* ignore */ } })
    srLinesRef.current = []
    try {
      const raw = snap.sr_levels
      const levels: number[] = typeof raw === 'string' ? JSON.parse(raw) : []
      srLinesRef.current = levels.map(lvl =>
        series.createPriceLine({
          price: lvl, color: '#374151',
          lineWidth: 1, lineStyle: LineStyle.Dashed,
          axisLabelVisible: false, title: '',
        })
      )
    } catch { /* ignore */ }
  }, [frame])

  const EMA_LEGEND = [
    { label: 'EMA 9',  color: '#ffffff' },
    { label: 'EMA 21', color: '#f472b6' },
    { label: 'EMA 34', color: '#facc15' },
    { label: 'EMA 89', color: '#3b82f6' },
  ]

  return (
    <div className={containerClassName ?? 'w-full h-full'} style={{ position: 'relative', minHeight: 200 }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      {/* EMA legend overlay */}
      <div style={{
        position: 'absolute', top: 6, left: 8,
        display: 'flex', flexDirection: 'column', gap: 2,
        pointerEvents: 'none',
      }}>
        {EMA_LEGEND.map(({ label, color }) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <div style={{ width: 16, height: 2, backgroundColor: color, borderRadius: 1 }} />
            <span style={{ color: '#8b949e', fontFamily: 'monospace', fontSize: 10 }}>{label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
