import useSWR from 'swr'
import { BASE_URL, type ChartInfo, type LogEntry, type ScriptMeta, type SyncStatus } from '@/lib/api'

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

export function useScripts() {
  return useSWR<{ scripts: ScriptMeta[] }>(`${BASE_URL}/api/scripts`, fetcher, {
    revalidateOnFocus: false,
  })
}

export function useSyncStatus() {
  // Polls while a sync is running (covers resuming after a page reload too)
  return useSWR<SyncStatus>(`${BASE_URL}/api/data/sync/status`, fetcher, {
    refreshInterval: (data) => (data?.status === 'running' ? 2000 : 0),
    revalidateOnFocus: false,
  })
}

export function useVersion() {
  return useSWR<{ status: string; version: string }>(
    `${BASE_URL}/api/health`,
    fetcher,
    { revalidateOnFocus: false },
  )
}
