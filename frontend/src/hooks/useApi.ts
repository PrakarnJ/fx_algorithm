import useSWR from 'swr'
import { BASE_URL, type ChartInfo, type LogEntry } from '@/lib/api'

const fetcher = (url: string) =>
  fetch(url).then((r) => {
    if (!r.ok) throw new Error(`API ${r.status}`)
    return r.json()
  })

export function useChartInfo() {
  return useSWR<ChartInfo>(`${BASE_URL}/api/chart/info`, fetcher, {
    revalidateOnFocus: false,
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
