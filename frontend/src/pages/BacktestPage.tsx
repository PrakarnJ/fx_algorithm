import { useState } from 'react'
import { RunConfigForm } from '@/components/backtest/RunConfigForm'
import { ProgressFeed } from '@/components/backtest/ProgressFeed'
import { TerminalCard } from '@/components/shared/TerminalCard'
import { RankingTable } from '@/components/dashboard/RankingTable'
import { Button } from '@/components/ui/button'
import { BarChart2 } from 'lucide-react'
import type { BacktestResult } from '@/lib/api'

export function BacktestPage() {
  const [jobId, setJobId] = useState<string | null>(null)
  const [results, setResults] = useState<BacktestResult[] | null>(null)

  function handleNewRun() {
    setJobId(null)
    setResults(null)
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Run Backtest</h1>
          <p className="text-sm text-muted-foreground font-mono mt-1">
            Select algorithms and symbols, then run a backtest job
          </p>
        </div>
        {results !== null && (
          <Button size="sm" onClick={handleNewRun} className="gap-1.5">
            <BarChart2 className="h-3.5 w-3.5" />
            New Run
          </Button>
        )}
      </div>

      {results !== null ? (
        <TerminalCard
          title={`Results — ${results.length} combo${results.length !== 1 ? 's' : ''}`}
        >
          <RankingTable results={results} />
        </TerminalCard>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <RunConfigForm onJobStarted={(id) => setJobId(id)} />

          {jobId ? (
            <ProgressFeed jobId={jobId} onComplete={setResults} />
          ) : (
            <TerminalCard title="Progress">
              <div className="flex flex-col items-center justify-center py-12 text-muted-foreground font-mono text-sm">
                <div className="text-3xl text-accent mb-3">_</div>
                No job running yet.
                <br />
                Configure and click Run Backtest.
              </div>
            </TerminalCard>
          )}
        </div>
      )}
    </div>
  )
}
