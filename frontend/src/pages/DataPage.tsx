import { useState, useEffect } from 'react'
import { ChevronDown, ChevronRight, Download, Trash2, RefreshCw, Database, CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { TerminalCard } from '@/components/shared/TerminalCard'
import { useStocks, useStockInfo } from '@/hooks/useApi'
import { apiFetch } from '@/lib/api'
import type { Stock, SyncJob } from '@/lib/api'
import { cn } from '@/lib/utils'

const TF_ORDER = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1', 'MN']

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toISOString().slice(0, 10)
}

function formatModified(ts: number): string {
  return new Date(ts * 1000).toLocaleString()
}

// ── Per-symbol expanded row ────────────────────────────────────────────────────

function SymbolDetail({ symbol, onDeleted: _onDeleted }: { symbol: string; onDeleted: () => void }) {
  const { data: info, mutate } = useStockInfo(symbol)
  const [busy, setBusy] = useState<string | null>(null)

  async function deleteTF(tf: string) {
    setBusy(`del-${tf}`)
    try {
      await apiFetch(`/api/stocks/${symbol}/${tf}`, { method: 'DELETE' })
      await mutate()
    } finally {
      setBusy(null)
    }
  }

  async function redownloadTF(tf: string) {
    setBusy(`dl-${tf}`)
    try {
      await apiFetch('/api/stocks/download', {
        method: 'POST',
        body: JSON.stringify({ symbols: [symbol], internal_tfs: [tf] }),
      })
      setTimeout(() => mutate(), 3000)
    } finally {
      setBusy(null)
    }
  }

  if (!info) {
    return (
      <tr>
        <td colSpan={7} className="px-6 py-4 font-mono text-xs text-muted-foreground">
          Loading…
        </td>
      </tr>
    )
  }

  const tfs = TF_ORDER.filter(tf => info[tf])

  if (tfs.length === 0) {
    return (
      <tr>
        <td colSpan={7} className="px-6 py-4 font-mono text-xs text-muted-foreground">
          No downloaded data files.
        </td>
      </tr>
    )
  }

  return (
    <>
      {tfs.map(tf => {
        const entry = info[tf]
        return (
          <tr key={tf} className="border-b border-card-border/30 bg-secondary/10">
            <td className="pl-12 pr-3 py-2 font-mono text-xs text-muted-foreground w-6" />
            <td className="px-3 py-2 font-mono text-xs text-accent font-semibold">{tf}</td>
            <td className="px-3 py-2 font-mono text-xs text-foreground text-right">
              {entry.bar_count.toLocaleString()}
            </td>
            <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
              {formatDate(entry.start_date)} → {formatDate(entry.end_date)}
            </td>
            <td className="px-3 py-2 font-mono text-xs text-muted-foreground text-right">
              {formatBytes(entry.file_size_bytes)}
            </td>
            <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
              {formatModified(entry.last_modified)}
            </td>
            <td className="px-3 py-2 text-right space-x-1">
              <Button
                size="sm"
                variant="outline"
                className="h-6 px-2 text-xs"
                disabled={busy !== null}
                onClick={() => redownloadTF(tf)}
              >
                <RefreshCw className={cn('h-3 w-3', busy === `dl-${tf}` && 'animate-spin')} />
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-6 px-2 text-xs text-sell hover:bg-sell/10 hover:border-sell"
                disabled={busy !== null}
                onClick={() => deleteTF(tf)}
              >
                <Trash2 className="h-3 w-3" />
              </Button>
            </td>
          </tr>
        )
      })}
    </>
  )
}

// ── Per-symbol summary row ─────────────────────────────────────────────────────

function SymbolRow({ stock, onDeleted }: { stock: Stock; onDeleted: () => void }) {
  const [expanded, setExpanded] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)

  async function deleteAll() {
    if (!confirm(`Delete all data for ${stock.symbol}?`)) return
    setBusy('del')
    try {
      await apiFetch(`/api/stocks/${stock.symbol}`, { method: 'DELETE' })
      onDeleted()
    } finally {
      setBusy(null)
    }
  }

  async function redownloadAll() {
    setBusy('dl')
    try {
      await apiFetch('/api/stocks/download', {
        method: 'POST',
        body: JSON.stringify({ symbols: [stock.symbol], internal_tfs: stock.available_tfs }),
      })
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <tr
        className="border-b border-card-border hover:bg-secondary/20 transition-colors cursor-pointer"
        onClick={() => setExpanded(e => !e)}
      >
        <td className="px-3 py-3 w-6">
          {expanded
            ? <ChevronDown className="h-4 w-4 text-accent" />
            : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
        </td>
        <td className="px-3 py-3 font-mono text-foreground font-semibold">{stock.symbol}</td>
        <td className="px-3 py-3 font-mono text-xs text-muted-foreground">{stock.name}</td>
        <td className="px-3 py-3">
          <div className="flex gap-1 flex-wrap">
            {stock.available_tfs.length === 0
              ? <span className="font-mono text-xs text-muted-foreground/50">no data</span>
              : stock.available_tfs.map(tf => (
                <span key={tf} className="font-mono text-xs px-1.5 py-0.5 bg-accent/10 text-accent rounded border border-accent/20">
                  {tf}
                </span>
              ))
            }
          </div>
        </td>
        <td className="px-3 py-3 font-mono text-xs text-foreground">
          {stock.last_data_date ?? '—'}
        </td>
        <td className="px-3 py-3 font-mono text-xs text-muted-foreground">
          {stock.last_synced ? formatModified(stock.last_synced) : '—'}
        </td>
        <td className="px-3 py-3 text-right" onClick={e => e.stopPropagation()}>
          <div className="flex items-center gap-1 justify-end">
            <Button
              size="sm"
              variant="outline"
              className="h-7 px-2 text-xs"
              disabled={busy !== null}
              onClick={redownloadAll}
              title="Re-download all timeframes"
            >
              <RefreshCw className={cn('h-3 w-3 mr-1', busy === 'dl' && 'animate-spin')} />
              Sync
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7 px-2 text-xs text-sell hover:bg-sell/10 hover:border-sell"
              disabled={busy !== null}
              onClick={deleteAll}
              title="Delete all data for this symbol"
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
        </td>
      </tr>

      {expanded && (
        <>
          <tr className="bg-secondary/5">
            <td className="pl-12 pr-3 py-1" />
            <td className="px-3 py-1 font-mono text-xs text-muted-foreground uppercase tracking-wider">TF</td>
            <td className="px-3 py-1 font-mono text-xs text-muted-foreground uppercase tracking-wider text-right">Bars</td>
            <td className="px-3 py-1 font-mono text-xs text-muted-foreground uppercase tracking-wider">Period</td>
            <td className="px-3 py-1 font-mono text-xs text-muted-foreground uppercase tracking-wider text-right">Size</td>
            <td className="px-3 py-1 font-mono text-xs text-muted-foreground uppercase tracking-wider">Updated</td>
            <td className="px-3 py-1 font-mono text-xs text-muted-foreground uppercase tracking-wider text-right">Actions</td>
          </tr>
          <SymbolDetail symbol={stock.symbol} onDeleted={onDeleted} />
        </>
      )}
    </>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function DataPage() {
  const { data: stocks, isLoading, error, mutate } = useStocks()
  const [syncJobId, setSyncJobId] = useState<string | null>(null)
  const [syncJob, setSyncJob] = useState<SyncJob | null>(null)

  // Derive global last-sync from the stocks data itself (updates after mutate())
  const globalLastSynced = stocks && stocks.length > 0
    ? Math.max(...stocks.map(s => s.last_synced ?? 0))
    : null

  // Poll sync job progress every 1.5 s until complete
  useEffect(() => {
    if (!syncJobId) return
    const iv = setInterval(async () => {
      try {
        const job = await apiFetch<SyncJob>(`/api/stocks/download/${syncJobId}`)
        setSyncJob(job)
        if (job.status === 'complete') {
          clearInterval(iv)
          setSyncJobId(null)
          mutate()
        }
      } catch {
        clearInterval(iv)
        setSyncJobId(null)
      }
    }, 1500)
    return () => clearInterval(iv)
  }, [syncJobId, mutate])

  async function handleSyncAll() {
    setSyncJob(null)
    const res = await apiFetch<{ job_id: string }>('/api/stocks/sync-all', { method: 'POST' })
    setSyncJobId(res.job_id)
  }

  const syncPct = syncJob && syncJob.total > 0
    ? Math.round((syncJob.done / syncJob.total) * 100)
    : 0

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Data Library</h1>
          <p className="text-sm text-muted-foreground font-mono mt-1">
            Manage downloaded OHLC datasets
            {globalLastSynced && globalLastSynced > 0 && (
              <span className="ml-3 text-muted-foreground">
                · last sync <span className="text-foreground">{formatModified(globalLastSynced)}</span>
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5"
            disabled={!!syncJobId}
            onClick={handleSyncAll}
            title="Incrementally sync all symbols to today"
          >
            <Download className={cn('h-3.5 w-3.5', syncJobId && 'animate-pulse')} />
            {syncJobId ? 'Syncing…' : 'Sync All'}
          </Button>
          <Button
            size="sm"
            className="gap-1.5"
            onClick={() => mutate()}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Sync progress panel */}
      {syncJob && (
        <div className="rounded-md border border-card-border bg-secondary/10 p-4 space-y-3">
          <div className="flex items-center justify-between font-mono text-xs text-muted-foreground">
            <span>Syncing {syncJob.done}/{syncJob.total} symbols</span>
            <span>{syncPct}%</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-secondary/40 overflow-hidden">
            <div
              className="h-full bg-accent rounded-full transition-all duration-300"
              style={{ width: `${syncPct}%` }}
            />
          </div>
          {syncJob.progress.length > 0 && (
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {syncJob.progress.map((entry, i) => (
                <div key={i} className="flex items-center gap-2 font-mono text-xs">
                  {entry.status === 'done'
                    ? <CheckCircle2 className="h-3 w-3 text-buy shrink-0" />
                    : <XCircle className="h-3 w-3 text-sell shrink-0" />}
                  <span className={entry.status === 'done' ? 'text-foreground' : 'text-sell'}>
                    {entry.symbol}
                  </span>
                  {entry.status === 'done' && entry.bars && (
                    <span className="text-muted-foreground">
                      {Object.entries(entry.bars).map(([tf, n]) => `${tf}: ${n.toLocaleString()}`).join(' · ')}
                    </span>
                  )}
                  {entry.status === 'error' && (
                    <span className="text-sell/70">{entry.error}</span>
                  )}
                </div>
              ))}
              {syncJobId && (
                <div className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin shrink-0" />
                  <span>fetching…</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}


      <TerminalCard title="Symbols">
        {isLoading ? (
          <div className="py-16 text-center font-mono text-sm text-muted-foreground">Loading…</div>
        ) : error ? (
          <div className="py-8 text-center font-mono text-sm text-sell">
            Failed to load. Is the backend running?
          </div>
        ) : !stocks || stocks.length === 0 ? (
          <div className="py-16 text-center text-muted-foreground font-mono text-sm">
            <Database className="h-10 w-10 mx-auto mb-3 opacity-20" />
            No symbols in registry. Add entries to stocks/registry.yaml.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-card-border">
                  <th className="px-3 py-3 w-6" />
                  <th className="px-3 py-3 font-mono text-xs text-muted-foreground uppercase tracking-wider text-left">Symbol</th>
                  <th className="px-3 py-3 font-mono text-xs text-muted-foreground uppercase tracking-wider text-left">Name</th>
                  <th className="px-3 py-3 font-mono text-xs text-muted-foreground uppercase tracking-wider text-left">Available TFs</th>
                  <th className="px-3 py-3 font-mono text-xs text-muted-foreground uppercase tracking-wider text-left">Data To</th>
                  <th className="px-3 py-3 font-mono text-xs text-muted-foreground uppercase tracking-wider text-left">Last Sync</th>
                  <th className="px-3 py-3 font-mono text-xs text-muted-foreground uppercase tracking-wider text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {stocks.map(stock => (
                  <SymbolRow key={stock.symbol} stock={stock} onDeleted={() => mutate()} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </TerminalCard>
    </div>
  )
}
