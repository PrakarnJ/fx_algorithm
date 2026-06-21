import { useBacktestResults } from '@/hooks/useApi'
import { RankingTable } from '@/components/dashboard/RankingTable'
import { TerminalCard } from '@/components/shared/TerminalCard'
import { Button } from '@/components/ui/button'
import { useNavigate } from 'react-router-dom'
import { Loader2, RefreshCw, BarChart2 } from 'lucide-react'

export function DashboardPage() {
  const navigate = useNavigate()
  const { data: results, isLoading, error, mutate } = useBacktestResults()

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">
            Strategy Rankings
          </h1>
          <p className="text-sm text-muted-foreground font-mono mt-1">
            Sorted by Profit Factor (out-of-sample)
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => mutate()}
            className="gap-1.5"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
          <Button
            size="sm"
            onClick={() => navigate('/backtest')}
            className="gap-1.5"
          >
            <BarChart2 className="h-3.5 w-3.5" />
            New Backtest
          </Button>
        </div>
      </div>

      {/* Table card */}
      <TerminalCard title="Results">
        {isLoading ? (
          <div className="flex items-center justify-center py-16 gap-2 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span className="font-mono text-sm">Loading results…</span>
          </div>
        ) : error ? (
          <div className="text-sell font-mono text-sm py-8 text-center">
            Failed to load results. Is the backend running?
            <br />
            <button
              onClick={() => mutate()}
              className="mt-2 text-accent hover:underline"
            >
              Retry
            </button>
          </div>
        ) : (
          <RankingTable results={results ?? []} />
        )}
      </TerminalCard>
    </div>
  )
}
