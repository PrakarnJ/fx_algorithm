import { useState } from 'react'
import { useLogs } from '@/hooks/useApi'
import { TerminalCard } from '@/components/shared/TerminalCard'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Loader2, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { formatDateTime } from '@/lib/formatters'
import type { LogEntry } from '@/lib/api'

function getEventTypes(logs: LogEntry[]): string[] {
  const types = new Set(logs.map(l => l.type))
  return Array.from(types).sort()
}

function LogDetails({ entry }: { entry: LogEntry }) {
  const { ts: _ts, type: _type, ...rest } = entry
  if (Object.keys(rest).length === 0) return null
  return (
    <span className="text-muted-foreground font-mono text-xs ml-2">
      {JSON.stringify(rest)}
    </span>
  )
}

function typeVariant(type: string): 'default' | 'success' | 'warning' | 'danger' | 'outline' {
  if (type.includes('error') || type.includes('fail')) return 'danger'
  if (type.includes('warn')) return 'warning'
  if (type.includes('trade') || type.includes('signal')) return 'success'
  if (type.includes('start') || type.includes('complete')) return 'default'
  return 'outline'
}

export function LogsPage() {
  const { data, isLoading, error, mutate } = useLogs(200)
  const [typeFilter, setTypeFilter] = useState<string>('all')

  const logs = data?.logs ?? []
  const eventTypes = getEventTypes(logs)
  const filtered = typeFilter === 'all' ? logs : logs.filter(l => l.type === typeFilter)

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Activity Logs</h1>
          <p className="text-sm text-muted-foreground font-mono mt-1">
            Auto-refreshes every 5 seconds
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={typeFilter} onValueChange={setTypeFilter}>
            <SelectTrigger className="w-40 h-8 text-xs">
              <SelectValue placeholder="Filter type…" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all" className="text-xs">All types</SelectItem>
              {eventTypes.map(t => (
                <SelectItem key={t} value={t} className="text-xs font-mono">
                  {t}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1.5"
            onClick={() => mutate()}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      <TerminalCard title={`Logs (${filtered.length})`}>
        {isLoading ? (
          <div className="flex items-center justify-center py-12 gap-2 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span className="font-mono text-sm">Loading…</span>
          </div>
        ) : error ? (
          <div className="text-sell font-mono text-sm py-8 text-center">
            Failed to load logs. Is the backend running?
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-muted-foreground font-mono text-sm py-8 text-center">
            No log entries found.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-card-border">
                  <th className="text-left px-3 py-2 font-mono text-muted-foreground uppercase tracking-wider w-36">
                    Time
                  </th>
                  <th className="text-left px-3 py-2 font-mono text-muted-foreground uppercase tracking-wider w-32">
                    Type
                  </th>
                  <th className="text-left px-3 py-2 font-mono text-muted-foreground uppercase tracking-wider">
                    Details
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((entry, idx) => (
                  <tr
                    key={idx}
                    className="border-b border-card-border/30 hover:bg-secondary/10 transition-colors"
                  >
                    <td className="px-3 py-2 font-mono text-muted-foreground whitespace-nowrap">
                      {formatDateTime(entry.ts)}
                    </td>
                    <td className="px-3 py-2">
                      <Badge variant={typeVariant(entry.type)} className="text-xs">
                        {entry.type}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 max-w-0">
                      <div className="truncate">
                        <LogDetails entry={entry} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </TerminalCard>
    </div>
  )
}
