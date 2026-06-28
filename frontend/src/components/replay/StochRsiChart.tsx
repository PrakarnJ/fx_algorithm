import { useEffect, useRef } from 'react'
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  LineStyle,
  CrosshairMode,
  type Time,
} from 'lightweight-charts'
import type { ReplayFrame } from '@/lib/api'

interface StochRsiChartProps {
  frame: ReplayFrame | null
  containerClassName?: string
}

function buildLineData(
  valueArr: Array<number | undefined>,
  timeArr: Array<Time | undefined>,
  upTo: number,
): LineData[] {
  const out: LineData[] = []
  for (let i = 0; i <= upTo; i++) {
    const v = valueArr[i]
    const t = timeArr[i]
    if (v !== undefined && t !== undefined) out.push({ time: t, value: v })
  }
  return out
}

export function StochRsiChart({ frame, containerClassName }: StochRsiChartProps) {
  const containerRef  = useRef<HTMLDivElement>(null)
  const chartRef      = useRef<IChartApi | null>(null)
  const kSeriesRef    = useRef<ISeriesApi<'Line'> | null>(null)
  const dSeriesRef    = useRef<ISeriesApi<'Line'> | null>(null)

  // Accumulated data for backward seek
  const kArr          = useRef<Array<number | undefined>>([])
  const dArr          = useRef<Array<number | undefined>>([])
  const timeArr       = useRef<Array<Time | undefined>>([])
  const drawnThroughRef = useRef<number>(-1)

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
      timeScale: { borderColor: '#1a2332', timeVisible: true, secondsVisible: false, visible: false },
      watermark: {
        visible: true,
        text: 'StochRSI(14)',
        fontSize: 10,
        color: 'rgba(139, 148, 158, 0.3)',
        horzAlign: 'left',
        vertAlign: 'top',
      },
    })

    const k = chart.addLineSeries({
      color: '#facc15',
      lineWidth: 1,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
      lastValueVisible: true,
      title: 'K',
    })
    const d = chart.addLineSeries({
      color: '#94a3b8',
      lineWidth: 1,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
      lastValueVisible: true,
      title: 'D',
    })

    // Overbought / oversold reference lines
    k.createPriceLine({ price: 70, color: '#ef444488', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: '70' })
    k.createPriceLine({ price: 30, color: '#22c55e88', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: '30' })
    k.createPriceLine({ price: 50, color: '#374151', lineWidth: 1, lineStyle: LineStyle.Solid, axisLabelVisible: false, title: '' })

    chartRef.current  = chart
    kSeriesRef.current = k
    dSeriesRef.current = d

    return () => {
      chart.remove()
      chartRef.current = kSeriesRef.current = dSeriesRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!frame || !kSeriesRef.current || !dSeriesRef.current) return

    const bi = frame.bar_index
    const timeSeconds = Math.floor(new Date(frame.bar_time).getTime() / 1000) as Time
    timeArr.current[bi] = timeSeconds

    const snap = frame.indicator_snapshot
    const kv = typeof snap.stochrsi_k === 'number' ? snap.stochrsi_k : undefined
    const dv = typeof snap.stochrsi_d === 'number' ? snap.stochrsi_d : undefined
    if (kv !== undefined) kArr.current[bi] = kv
    if (dv !== undefined) dArr.current[bi] = dv

    const isSeeking = bi <= drawnThroughRef.current

    if (isSeeking) {
      kSeriesRef.current.setData(buildLineData(kArr.current, timeArr.current, bi))
      dSeriesRef.current.setData(buildLineData(dArr.current, timeArr.current, bi))
      drawnThroughRef.current = bi
    } else {
      drawnThroughRef.current = bi
      chartRef.current?.timeScale().scrollToPosition(0, false)
      if (kv !== undefined) kSeriesRef.current.update({ time: timeSeconds, value: kv })
      if (dv !== undefined) dSeriesRef.current.update({ time: timeSeconds, value: dv })
    }
  }, [frame])

  return (
    <div
      ref={containerRef}
      className={containerClassName ?? 'w-full h-full'}
      style={{ minHeight: 80 }}
    />
  )
}
