import { useEffect, useRef } from 'react'
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
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

export function CandlestickChart({ frame, containerClassName }: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const slLineRef = useRef<IPriceLine | null>(null)
  const tpLineRef = useRef<IPriceLine | null>(null)
  const markersRef = useRef<SeriesMarker<Time>[]>([])

  // Initialize chart once on mount — use autoSize so dimensions resolve correctly
  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      autoSize: true,          // fills container; no explicit width/height needed
      layout: {
        background: { color: '#0d1117' },
        textColor: '#8b949e',
      },
      grid: {
        vertLines: { color: '#1a2332' },
        horzLines: { color: '#1a2332' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#1a2332' },
      timeScale: {
        borderColor: '#1a2332',
        timeVisible: true,
        secondsVisible: false,
      },
    })

    const series = chart.addCandlestickSeries({
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderUpColor: '#22c55e',
      borderDownColor: '#ef4444',
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    })

    chartRef.current = chart
    seriesRef.current = series
    markersRef.current = []

    return () => {
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
      markersRef.current = []
    }
  }, [])

  // Update chart on each new frame
  useEffect(() => {
    if (!frame || !seriesRef.current) return

    const series = seriesRef.current

    // bar_time is ISO string — convert to UTC seconds for lightweight-charts
    const timeSeconds = Math.floor(new Date(frame.bar_time).getTime() / 1000) as Time

    const bar: CandlestickData = {
      time: timeSeconds,
      open: frame.bar.open,
      high: frame.bar.high,
      low: frame.bar.low,
      close: frame.bar.close,
    }
    series.update(bar)

    // Auto-scroll: pin right edge of time axis to the most-recent bar
    chartRef.current?.timeScale().scrollToPosition(0, false)

    // Signal markers — direction is lowercase from backend ("buy" / "sell")
    if (frame.signal) {
      const isBuy = frame.signal.direction === 'buy'
      const newMarker: SeriesMarker<Time> = {
        time: timeSeconds,
        position: isBuy ? 'belowBar' : 'aboveBar',
        color: isBuy ? '#22c55e' : '#ef4444',
        shape: isBuy ? 'arrowUp' : 'arrowDown',
        text: isBuy ? 'BUY' : 'SELL',
      }
      // Cap at 500 markers to prevent setMarkers() from degrading at high bar counts
      markersRef.current = [...markersRef.current.slice(-499), newMarker]
      series.setMarkers(markersRef.current)
    }

    // Remove old SL/TP lines before placing new ones
    if (slLineRef.current) {
      series.removePriceLine(slLineRef.current)
      slLineRef.current = null
    }
    if (tpLineRef.current) {
      series.removePriceLine(tpLineRef.current)
      tpLineRef.current = null
    }

    if (frame.open_trade) {
      slLineRef.current = series.createPriceLine({
        price: frame.open_trade.sl,
        color: '#ef4444',
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: 'SL',
      })
      tpLineRef.current = series.createPriceLine({
        price: frame.open_trade.tp,
        color: '#22c55e',
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: 'TP',
      })
    }
  }, [frame])

  return (
    <div
      ref={containerRef}
      className={containerClassName ?? 'w-full h-full'}
      style={{ minHeight: 300 }}
    />
  )
}
