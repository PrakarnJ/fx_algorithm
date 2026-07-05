import { useEffect, useRef } from 'react'
import {
  createChart,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type SeriesType,
  type SeriesMarker,
  type CandlestickData,
  type LineData,
  type HistogramData,
  type Time,
} from 'lightweight-charts'
import type { PineBacktestResponse } from '@/lib/api'

const CHART_OPTS = {
  layout: { background: { color: '#0d1117' }, textColor: '#8b949e' },
  grid: { vertLines: { color: '#1a2332' }, horzLines: { color: '#1a2332' } },
  crosshair: { mode: CrosshairMode.Normal },
  rightPriceScale: { borderColor: '#1a2332' },
  timeScale: { borderColor: '#1a2332', timeVisible: true, secondsVisible: false },
}

// Pine shape name → lightweight-charts marker shape
function markerShape(shape: string): SeriesMarker<Time>['shape'] {
  if (shape.includes('down')) return 'arrowDown'
  if (shape.includes('up')) return 'arrowUp'
  if (shape === 'circle') return 'circle'
  return 'square'
}

interface Props {
  result: PineBacktestResponse | null
}

export function PineChart({ result }: Props) {
  const priceRef = useRef<HTMLDivElement>(null)
  const paneRef = useRef<HTMLDivElement>(null)
  const priceChart = useRef<IChartApi | null>(null)
  const paneChart = useRef<IChartApi | null>(null)
  const candleSeries = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const dynamicSeries = useRef<ISeriesApi<SeriesType>[]>([])
  const paneSeries = useRef<ISeriesApi<SeriesType>[]>([])

  const hasPane = !!result && result.plots.some((p) => !p.overlay)

  // ── mount charts once ────────────────────────────────────────────────────
  useEffect(() => {
    if (!priceRef.current) return
    const pc = createChart(priceRef.current, {
      ...CHART_OPTS,
      width: priceRef.current.clientWidth,
      height: priceRef.current.clientHeight,
    })
    priceChart.current = pc
    candleSeries.current = pc.addCandlestickSeries({
      upColor: '#22c55e', downColor: '#ef4444',
      borderUpColor: '#22c55e', borderDownColor: '#ef4444',
      wickUpColor: '#22c55e', wickDownColor: '#ef4444',
    })

    if (paneRef.current) {
      const oc = createChart(paneRef.current, {
        ...CHART_OPTS,
        width: paneRef.current.clientWidth,
        height: paneRef.current.clientHeight,
      })
      paneChart.current = oc
      // keep panes time-aligned
      pc.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (range) paneChart.current?.timeScale().setVisibleLogicalRange(range)
      })
    }

    const ro = new ResizeObserver(() => {
      if (priceRef.current) pc.applyOptions({ width: priceRef.current.clientWidth, height: priceRef.current.clientHeight })
      if (paneRef.current && paneChart.current) paneChart.current.applyOptions({ width: paneRef.current.clientWidth, height: paneRef.current.clientHeight })
    })
    if (priceRef.current) ro.observe(priceRef.current)
    if (paneRef.current) ro.observe(paneRef.current)

    return () => {
      ro.disconnect()
      pc.remove()
      paneChart.current?.remove()
      priceChart.current = null
      paneChart.current = null
      candleSeries.current = null
      dynamicSeries.current = []
      paneSeries.current = []
    }
  }, [])

  // ── render backtest result ───────────────────────────────────────────────
  useEffect(() => {
    const pc = priceChart.current
    const cs = candleSeries.current
    if (!pc || !cs) return

    dynamicSeries.current.forEach((s) => pc.removeSeries(s))
    dynamicSeries.current = []
    const oc = paneChart.current
    if (oc) {
      paneSeries.current.forEach((s) => oc.removeSeries(s))
      paneSeries.current = []
    }

    if (!result || !result.ok || result.bars.length === 0) {
      cs.setData([])
      cs.setMarkers([])
      return
    }

    const times = result.bars.map((b) => b.time as Time)

    cs.setData(result.bars.map((b): CandlestickData => ({
      time: b.time as Time, open: b.open, high: b.high, low: b.low, close: b.close,
    })))

    // plot() series — overlay on price pane, rest on the indicator pane
    for (const plot of result.plots) {
      const target = plot.overlay ? pc : oc
      const bucket = plot.overlay ? dynamicSeries.current : paneSeries.current
      if (!target) continue
      const data = plot.values
        .map((v, i) => (v !== null && isFinite(v) ? { time: times[i], value: v } : null))
        .filter((d): d is LineData => d !== null)
      let s: ISeriesApi<SeriesType>
      if (plot.style === 'histogram') {
        s = target.addHistogramSeries({ color: plot.color, priceLineVisible: false, lastValueVisible: false })
        s.setData(data as HistogramData[])
      } else {
        s = target.addLineSeries({
          color: plot.color,
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
          title: plot.title,
        })
        s.setData(data)
      }
      bucket.push(s)
    }

    // hline() — flat reference lines (drawn on whichever pane has plots)
    for (const hl of result.hlines) {
      const target = hasPane && oc ? oc : pc
      const bucket = hasPane && oc ? paneSeries.current : dynamicSeries.current
      const s = target.addLineSeries({
        color: hl.color, lineWidth: 1, lineStyle: 2,
        priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
      })
      s.setData(times.map((t) => ({ time: t, value: hl.price })))
      bucket.push(s)
    }

    // markers: plotshape() + trade entries/exits
    const markers: SeriesMarker<Time>[] = []
    for (const sh of result.shapes) {
      markers.push({
        time: sh.time as Time,
        position: sh.location === 'abovebar' ? 'aboveBar' : 'belowBar',
        shape: markerShape(sh.shape),
        color: sh.color,
        text: sh.text || undefined,
      })
    }
    for (const t of result.trades) {
      markers.push({
        time: t.entry_time as Time,
        position: t.direction === 'long' ? 'belowBar' : 'aboveBar',
        shape: t.direction === 'long' ? 'arrowUp' : 'arrowDown',
        color: t.direction === 'long' ? '#22c55e' : '#ef4444',
        text: `${t.direction === 'long' ? 'Buy' : 'Sell'} ${t.entry_id}`,
      })
      if (t.exit_time !== null && t.exit_price !== null) {
        markers.push({
          time: t.exit_time as Time,
          position: t.direction === 'long' ? 'aboveBar' : 'belowBar',
          shape: 'square',
          color: (t.profit ?? 0) >= 0 ? '#22c55e' : '#ef4444',
          text: `Exit ${t.exit_reason}`,
        })
      }
    }
    markers.sort((a, b) => (a.time as number) - (b.time as number))
    cs.setMarkers(markers)

    pc.timeScale().fitContent()
    oc?.timeScale().fitContent()
  }, [result, hasPane])

  return (
    <div className="flex flex-col h-full">
      <div ref={priceRef} className="flex-1" style={{ minHeight: 0 }} />
      <div
        ref={paneRef}
        className={`border-t border-card-border ${hasPane ? 'block' : 'hidden'}`}
        style={{ height: '28%', minHeight: hasPane ? 80 : 0 }}
      />
    </div>
  )
}
