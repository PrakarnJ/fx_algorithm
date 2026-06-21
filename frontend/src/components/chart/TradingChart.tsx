import { useEffect, useRef, useMemo } from 'react'
import {
  createChart,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type SeriesType,
  type CandlestickData,
  type LineData,
  type Time,
} from 'lightweight-charts'
import { ema, rsi, atr, bollingerBands, adx } from '@/lib/indicators'
import type { OHLCBar } from '@/lib/api'
import type { IndicatorSettings } from './IndicatorConfig'

const CHART_OPTS = {
  layout: { background: { color: '#0d1117' }, textColor: '#8b949e' },
  grid: { vertLines: { color: '#1a2332' }, horzLines: { color: '#1a2332' } },
  crosshair: { mode: CrosshairMode.Normal },
  rightPriceScale: { borderColor: '#1a2332' },
  timeScale: { borderColor: '#1a2332', timeVisible: true, secondsVisible: false },
}

interface Props {
  bars: OHLCBar[]
  indicators: IndicatorSettings
  currentBarIndex: number | null
}

export function TradingChart({ bars, indicators, currentBarIndex }: Props) {
  const priceRef = useRef<HTMLDivElement>(null)
  const oscRef = useRef<HTMLDivElement>(null)
  const priceChart = useRef<IChartApi | null>(null)
  const oscChart = useRef<IChartApi | null>(null)
  const candleSeries = useRef<ISeriesApi<'Candlestick'> | null>(null)
  // Track overlay series so we can remove them on re-render
  const overlaySeries = useRef<ISeriesApi<SeriesType>[]>([])
  const oscSeries = useRef<ISeriesApi<SeriesType>[]>([])
  const crosshairSync = useRef(false)

  const visibleBars = useMemo(() => {
    if (currentBarIndex === null) return bars
    return bars.slice(0, currentBarIndex + 1)
  }, [bars, currentBarIndex])

  const closes = useMemo(() => visibleBars.map(b => b.close), [visibleBars])
  const highs  = useMemo(() => visibleBars.map(b => b.high),  [visibleBars])
  const lows   = useMemo(() => visibleBars.map(b => b.low),   [visibleBars])

  // ── Mount charts once ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!priceRef.current) return

    const pc = createChart(priceRef.current, {
      ...CHART_OPTS,
      width: priceRef.current.clientWidth,
      height: priceRef.current.clientHeight,
    })
    priceChart.current = pc

    const cs = pc.addCandlestickSeries({
      upColor: '#22c55e', downColor: '#ef4444',
      borderUpColor: '#22c55e', borderDownColor: '#ef4444',
      wickUpColor: '#22c55e', wickDownColor: '#ef4444',
    })
    candleSeries.current = cs

    if (oscRef.current) {
      const oc = createChart(oscRef.current, {
        ...CHART_OPTS,
        width: oscRef.current.clientWidth,
        height: oscRef.current.clientHeight,
      })
      oscChart.current = oc

      // Sync crosshair
      pc.subscribeCrosshairMove(param => {
        if (crosshairSync.current || !param.time) return
        crosshairSync.current = true
        oc.timeScale().setVisibleRange(pc.timeScale().getVisibleRange()!)
        crosshairSync.current = false
      })
    }

    const ro = new ResizeObserver(() => {
      if (priceRef.current) pc.applyOptions({ width: priceRef.current.clientWidth, height: priceRef.current.clientHeight })
      if (oscRef.current && oscChart.current) oscChart.current.applyOptions({ width: oscRef.current.clientWidth, height: oscRef.current.clientHeight })
    })
    if (priceRef.current) ro.observe(priceRef.current)
    if (oscRef.current) ro.observe(oscRef.current)

    return () => {
      ro.disconnect()
      pc.remove()
      oscChart.current?.remove()
      priceChart.current = null
      oscChart.current = null
      candleSeries.current = null
      overlaySeries.current = []
      oscSeries.current = []
    }
  }, [])

  // ── Update candles ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (!candleSeries.current) return
    const data: CandlestickData[] = visibleBars.map(b => ({
      time: b.time as Time,
      open: b.open, high: b.high, low: b.low, close: b.close,
    }))
    candleSeries.current.setData(data)
    if (currentBarIndex !== null) priceChart.current?.timeScale().scrollToRealTime()
  }, [visibleBars, currentBarIndex])

  // ── Overlay series (EMA / Bollinger) ────────────────────────────────────────
  useEffect(() => {
    const pc = priceChart.current
    if (!pc) return

    // Remove previous overlays
    overlaySeries.current.forEach(s => pc.removeSeries(s))
    overlaySeries.current = []
    if (closes.length === 0) return

    const times = visibleBars.map(b => b.time as Time)

    function addLine(data: (number | null)[], color: string, lineWidth: 1 | 2 = 1) {
      const s = pc!.addLineSeries({ color, lineWidth, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false })
      const ld: LineData[] = data
        .map((v, i) => v !== null && isFinite(v) ? { time: times[i], value: v } : null)
        .filter((d): d is LineData => d !== null)
      s.setData(ld)
      overlaySeries.current.push(s)
    }

    if (indicators.emaFast.enabled) addLine(ema(closes, indicators.emaFast.period), '#f59e0b')
    if (indicators.emaSlow.enabled) addLine(ema(closes, indicators.emaSlow.period), '#6366f1')
    if (indicators.bb.enabled) {
      const bb = bollingerBands(closes, indicators.bb.period, indicators.bb.mult)
      addLine(bb.upper,  '#64748b')
      addLine(bb.middle, '#94a3b8')
      addLine(bb.lower,  '#64748b')
    }
  }, [visibleBars, closes, indicators.emaFast, indicators.emaSlow, indicators.bb])

  // ── Oscillator series ────────────────────────────────────────────────────────
  useEffect(() => {
    const oc = oscChart.current
    if (!oc) return

    oscSeries.current.forEach(s => oc.removeSeries(s))
    oscSeries.current = []
    if (closes.length === 0 || !indicators.oscillator) return

    const times = visibleBars.map(b => b.time as Time)
    let values: (number | null)[] = []
    if (indicators.oscillator === 'rsi') values = rsi(closes, indicators.rsiPeriod)
    else if (indicators.oscillator === 'atr') values = atr(highs, lows, closes, indicators.atrPeriod)
    else if (indicators.oscillator === 'adx') values = adx(highs, lows, closes, indicators.adxPeriod)

    const color = indicators.oscillator === 'rsi' ? '#a855f7'
      : indicators.oscillator === 'atr' ? '#06b6d4' : '#f97316'

    function addOsc(data: (number | null)[], col: string, lineWidth: 1 | 2 = 1) {
      const s = oc!.addLineSeries({ color: col, lineWidth, lastValueVisible: false, priceLineVisible: false })
      const ld: LineData[] = data
        .map((v, i) => v !== null && isFinite(v) ? { time: times[i], value: v } : null)
        .filter((d): d is LineData => d !== null)
      s.setData(ld)
      oscSeries.current.push(s)
    }

    addOsc(values, color)

    if (indicators.oscillator === 'rsi') {
      // Draw overbought/oversold reference lines using the same time axis
      const refData: LineData[] = times.map(t => ({ time: t, value: 70 }))
      const refDataLow: LineData[] = times.map(t => ({ time: t, value: 30 }))
      const ob = oc.addLineSeries({ color: '#ef4444', lineWidth: 1, lastValueVisible: false, priceLineVisible: false })
      const os = oc.addLineSeries({ color: '#22c55e', lineWidth: 1, lastValueVisible: false, priceLineVisible: false })
      ob.setData(refData)
      os.setData(refDataLow)
      oscSeries.current.push(ob, os)
    }
  }, [visibleBars, closes, highs, lows, indicators.oscillator, indicators.rsiPeriod, indicators.atrPeriod, indicators.adxPeriod])

  return (
    <div className="flex flex-col h-full">
      <div ref={priceRef} className="flex-1" style={{ minHeight: 0 }} />
      <div
        ref={oscRef}
        className={`border-t border-card-border transition-all ${indicators.oscillator ? 'block' : 'hidden'}`}
        style={{ height: '28%', minHeight: indicators.oscillator ? 80 : 0 }}
      />
    </div>
  )
}
