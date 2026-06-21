import useSWR from 'swr'
import { BASE_URL, type Algorithm, type BacktestResult, type Stock, type LogEntry, type StockTFInfo, type OHLCBar } from '@/lib/api'

const fetcher = (url: string) =>
  fetch(url).then((r) => {
    if (!r.ok) throw new Error(`API ${r.status}`)
    return r.json()
  })

export function useAlgorithms() {
  return useSWR<Algorithm[]>(`${BASE_URL}/api/algorithms`, fetcher)
}

export function useStocks() {
  return useSWR<Stock[]>(`${BASE_URL}/api/stocks`, fetcher)
}

export function useBacktestResults() {
  return useSWR<BacktestResult[]>(`${BASE_URL}/api/backtest/results`, fetcher, {
    refreshInterval: 0,
  })
}

export function useLogs(limit = 200) {
  return useSWR<{ logs: LogEntry[] }>(
    `${BASE_URL}/api/logs?limit=${limit}`,
    fetcher,
    { refreshInterval: 5000 },
  )
}

export function useVersion() {
  return useSWR<{ status: string; version: string }>(
    `${BASE_URL}/api/health`,
    fetcher,
    { revalidateOnFocus: false },
  )
}

export function useStockInfo(symbol: string | null) {
  return useSWR<StockTFInfo>(
    symbol ? `${BASE_URL}/api/stocks/${symbol}/info` : null,
    fetcher,
    { revalidateOnFocus: false },
  )
}

export function useStockBars(symbol: string | null, tf: string, limit = 10000) {
  return useSWR<{ symbol: string; tf: string; bars: OHLCBar[] }>(
    symbol ? `${BASE_URL}/api/stocks/${encodeURIComponent(symbol)}/data?tf=${tf}&limit=${limit}` : null,
    fetcher,
    { revalidateOnFocus: false },
  )
}
