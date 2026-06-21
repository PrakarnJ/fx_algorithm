import { useState } from 'react'
import { ChevronDown, ChevronRight, Download, Trash2, RefreshCw, Database } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { TerminalCard } from '@/components/shared/TerminalCard'
import { useStocks, useStockInfo } from '@/hooks/useApi'
import { apiFetch } from '@/lib/api'
import type { Stock } from '@/lib/api'
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

function SymbolDetail({ symbol, onDeleted }: { symbol: string; onDeleted: () => void }) {
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

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Data Library</h1>
          <p className="text-sm text-muted-foreground font-mono mt-1">
            Manage downloaded OHLC datasets
          </p>
        </div>
        <Button
          size="sm"
          className="gap-1.5"
          onClick={() => mutate()}
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </Button>
      </div>

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
