import { useCallback, useEffect, useRef, useState } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { javascript } from '@codemirror/lang-javascript'
import { oneDark } from '@codemirror/theme-one-dark'
import { FilePlus2, LoaderCircle, Pencil, Play, RefreshCw, Save, Trash2 } from 'lucide-react'
import { PineChart } from '@/components/pine/PineChart'
import { StrategyTester } from '@/components/pine/StrategyTester'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useChartInfo, useScripts, useSyncStatus } from '@/hooks/useApi'
import {
  createScript, deleteScript, getScript, runPineBacktest, startDataSync,
  updateScript, type PineBacktestResponse,
} from '@/lib/api'
import { formatDateTime } from '@/lib/formatters'
import { cn } from '@/lib/utils'

const DEFAULT_SCRIPT = `//@version=6
strategy("EMA Cross", overlay=true, initial_capital=100000, default_qty_value=10)

fastLen = input.int(9, title="Fast EMA")
slowLen = input.int(21, title="Slow EMA")

fast = ta.ema(close, fastLen)
slow = ta.ema(close, slowLen)

plot(fast, "Fast EMA", color.orange)
plot(slow, "Slow EMA", color.blue)

longCond = ta.crossover(fast, slow)
shortCond = ta.crossunder(fast, slow)

if longCond
    strategy.entry("L", strategy.long)
if shortCond
    strategy.entry("S", strategy.short)
`

const STORAGE_KEY = 'pine-studio-script'
const SCRIPT_ID_KEY = 'pine-studio-script-id'
const DRAFT = 'draft'
const TIMEFRAMES = ['M15', 'H1', 'H4']

export function PineStudioPage() {
  const [source, setSource] = useState<string>(
    () => localStorage.getItem(STORAGE_KEY) ?? DEFAULT_SCRIPT,
  )
  const [timeframe, setTimeframe] = useState('M15')
  const [startDate, setStartDate] = useState('2025-01-01')
  const [endDate, setEndDate] = useState('')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<PineBacktestResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Saved-script state: which DB script is loaded + its source at load/save time
  const [activeScriptId, setActiveScriptId] = useState<number | null>(() => {
    const raw = localStorage.getItem(SCRIPT_ID_KEY)
    return raw ? Number(raw) : null
  })
  const [loadedSnapshot, setLoadedSnapshot] = useState<string | null>(null)
  const [scriptBusy, setScriptBusy] = useState(false)

  const { data: info, mutate: mutateInfo } = useChartInfo()
  const { data: scriptList, mutate: mutateScripts } = useScripts()
  const { data: syncStatus, mutate: mutateSync } = useSyncStatus()
  const syncRunning = syncStatus?.status === 'running'

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, source)
  }, [source])

  useEffect(() => {
    if (activeScriptId === null) localStorage.removeItem(SCRIPT_ID_KEY)
    else localStorage.setItem(SCRIPT_ID_KEY, String(activeScriptId))
  }, [activeScriptId])

  // On mount: restore the loaded-script snapshot so the dirty dot is accurate
  useEffect(() => {
    if (activeScriptId === null) return
    getScript(activeScriptId)
      .then((s) => setLoadedSnapshot(s.source))
      .catch(() => setActiveScriptId(null))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Refresh chart info when a sync finishes
  const prevSyncStatus = useRef<string | undefined>(undefined)
  useEffect(() => {
    if (prevSyncStatus.current === 'running' && syncStatus?.status !== 'running') {
      void mutateInfo()
    }
    prevSyncStatus.current = syncStatus?.status
  }, [syncStatus?.status, mutateInfo])

  const dirty = activeScriptId !== null && loadedSnapshot !== null && source !== loadedSnapshot
  const activeScript = scriptList?.scripts.find((s) => s.id === activeScriptId)

  const loadScript = async (value: string) => {
    if (value === DRAFT) {
      setActiveScriptId(null)
      setLoadedSnapshot(null)
      return
    }
    try {
      const s = await getScript(Number(value))
      setSource(s.source)
      setActiveScriptId(s.id)
      setLoadedSnapshot(s.source)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const saveAs = async () => {
    let name = window.prompt('Script name')
    while (name !== null) {
      try {
        const s = await createScript(name, source)
        setActiveScriptId(s.id)
        setLoadedSnapshot(source)
        await mutateScripts()
        return
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e)
        name = window.prompt(
          msg.includes('409') ? `"${name}" already exists — pick another name` : msg,
          name,
        )
      }
    }
  }

  const save = async () => {
    setScriptBusy(true)
    try {
      if (activeScriptId === null) {
        await saveAs()
      } else {
        await updateScript(activeScriptId, { source })
        setLoadedSnapshot(source)
        await mutateScripts()
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setScriptBusy(false)
    }
  }

  const rename = async () => {
    if (activeScriptId === null || !activeScript) return
    const name = window.prompt('New name', activeScript.name)
    if (!name || name === activeScript.name) return
    try {
      await updateScript(activeScriptId, { name })
      await mutateScripts()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const remove = async () => {
    if (activeScriptId === null || !activeScript) return
    if (!window.confirm(`Delete script "${activeScript.name}"?`)) return
    try {
      await deleteScript(activeScriptId)
      setActiveScriptId(null)
      setLoadedSnapshot(null)
      await mutateScripts()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const sync = async () => {
    if (syncRunning) return
    if (!info?.last_synced) {
      const ok = window.confirm(
        'First sync replaces the current (synthetic) data with full real Dukascopy history — a multi-year M15 download that takes several minutes. Continue?',
      )
      if (!ok) return
    }
    try {
      await startDataSync('auto')
      await mutateSync()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const run = useCallback(async () => {
    setRunning(true)
    setError(null)
    try {
      const res = await runPineBacktest({
        source,
        timeframe,
        start_date: startDate || null,
        end_date: endDate || null,
      })
      setResult(res)
      if (!res.ok && res.errors.length > 0) {
        const e = res.errors[0]
        setError(`Line ${e.line}:${e.col} — ${e.message}`)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(false)
    }
  }, [source, timeframe, startDate, endDate])

  // Ctrl/Cmd+Enter runs the script
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault()
        void run()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [run])

  const tfInfo = info?.timeframes?.[timeframe]

  return (
    <div className="flex flex-col h-screen">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-card-border">
        {/* Saved scripts */}
        <div className="flex items-center gap-1">
          <Select value={activeScriptId !== null ? String(activeScriptId) : DRAFT}
                  onValueChange={(v) => void loadScript(v)}>
            <SelectTrigger className="w-44 h-8 text-xs font-mono">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={DRAFT} className="text-xs font-mono">— draft —</SelectItem>
              {scriptList?.scripts.map((s) => (
                <SelectItem key={s.id} value={String(s.id)} className="text-xs font-mono">
                  {s.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {dirty && <span className="text-accent text-lg leading-none" title="Unsaved changes">●</span>}
          <button onClick={() => void save()} disabled={scriptBusy} title="Save (updates the selected script)"
                  className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-secondary disabled:opacity-50">
            <Save className="h-4 w-4" />
          </button>
          <button onClick={() => void saveAs()} title="Save as new script"
                  className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-secondary">
            <FilePlus2 className="h-4 w-4" />
          </button>
          <button onClick={() => void rename()} disabled={activeScriptId === null} title="Rename script"
                  className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-secondary disabled:opacity-30">
            <Pencil className="h-4 w-4" />
          </button>
          <button onClick={() => void remove()} disabled={activeScriptId === null} title="Delete script"
                  className="p-1.5 rounded text-muted-foreground hover:text-red-400 hover:bg-secondary disabled:opacity-30">
            <Trash2 className="h-4 w-4" />
          </button>
        </div>

        <span className="font-mono text-sm font-bold text-accent">XAUUSD</span>
        <div className="flex rounded-md border border-card-border overflow-hidden">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={cn(
                'px-3 py-1 text-xs font-mono transition-colors',
                timeframe === tf
                  ? 'bg-accent/15 text-accent'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {tf}
            </button>
          ))}
        </div>
        <input
          type="date"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
          className="bg-secondary border border-card-border rounded px-2 py-1 text-xs font-mono"
        />
        <span className="text-muted-foreground text-xs">→</span>
        <input
          type="date"
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
          className="bg-secondary border border-card-border rounded px-2 py-1 text-xs font-mono"
        />
        {tfInfo && (
          <span className="text-xs text-muted-foreground font-mono">
            {tfInfo.bars.toLocaleString()} bars · {tfInfo.start} → {tfInfo.end}
          </span>
        )}

        {/* Data sync */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => void sync()}
            disabled={syncRunning}
            title="Sync XAUUSD data from Dukascopy"
            className="flex items-center gap-1.5 px-2 py-1 rounded border border-card-border text-xs
                       text-muted-foreground hover:text-foreground hover:bg-secondary disabled:opacity-50"
          >
            <RefreshCw className={cn('h-3.5 w-3.5', syncRunning && 'animate-spin')} />
            {syncRunning ? 'Syncing…' : 'Sync'}
          </button>
          <span className="text-xs font-mono text-muted-foreground">
            {syncRunning
              ? syncStatus?.step
              : syncStatus?.status === 'error'
                ? <span className="text-red-400" title={syncStatus.error ?? ''}>sync failed</span>
                : info?.last_synced
                  ? `synced ${formatDateTime(info.last_synced)}`
                  : 'never synced'}
          </span>
        </div>

        <button
          onClick={() => void run()}
          disabled={running}
          className="ml-auto flex items-center gap-2 bg-accent/15 text-accent border border-accent/30
                     rounded-md px-4 py-1.5 text-sm font-semibold hover:bg-accent/25
                     disabled:opacity-50 transition-colors"
        >
          {running
            ? <LoaderCircle className="h-4 w-4 animate-spin" />
            : <Play className="h-4 w-4" />}
          {running ? 'Running…' : 'Run'}
          <span className="text-xs text-muted-foreground font-mono">⌘⏎</span>
        </button>
      </div>

      {/* Editor | Chart */}
      <div className="flex flex-1 min-h-0">
        <div className="w-[420px] flex-shrink-0 border-r border-card-border flex flex-col min-h-0">
          <div className="px-3 py-1.5 text-xs text-muted-foreground border-b border-card-border">
            Pine Script <span className="text-muted-foreground/60">(v4–v6 subset)</span>
          </div>
          <div className="flex-1 overflow-auto">
            <CodeMirror
              value={source}
              onChange={setSource}
              theme={oneDark}
              extensions={[javascript()]}
              basicSetup={{ lineNumbers: true, foldGutter: false, highlightActiveLine: true }}
              style={{ fontSize: 13, height: '100%' }}
            />
          </div>
          {error && (
            <div className="px-3 py-2 text-xs font-mono text-red-400 bg-red-950/40 border-t border-red-900/50 whitespace-pre-wrap">
              {error}
            </div>
          )}
        </div>
        <div className="flex-1 min-w-0 flex flex-col">
          {result && result.ok ? (
            <PineChart result={result} />
          ) : (
            <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">
              {running ? 'Running backtest…' : 'Paste a Pine Script and press Run (⌘⏎)'}
            </div>
          )}
        </div>
      </div>

      {/* Strategy Tester */}
      <StrategyTester result={result} />
    </div>
  )
}
