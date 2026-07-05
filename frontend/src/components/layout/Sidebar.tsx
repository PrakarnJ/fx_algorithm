import { NavLink } from 'react-router-dom'
import { CandlestickChart, ScrollText } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useVersion } from '@/hooks/useApi'

const navItems = [
  { to: '/', label: 'Studio', icon: CandlestickChart, end: true },
  { to: '/logs', label: 'Logs', icon: ScrollText, end: false },
]

export function Sidebar() {
  const { data: health } = useVersion()

  return (
    <aside className="w-48 min-h-screen bg-background border-r border-card-border flex flex-col flex-shrink-0">
      {/* Logo / Title */}
      <div className="px-6 py-5 border-b border-card-border">
        <div className="font-mono text-accent text-sm font-bold tracking-widest uppercase">
          PINE_STUDIO
        </div>
        <div className="font-mono text-muted-foreground text-xs mt-0.5">
          XAUUSD Backtester
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                isActive
                  ? 'bg-accent/10 text-accent border border-accent/30'
                  : 'text-muted-foreground hover:text-foreground hover:bg-secondary',
              )
            }
          >
            <Icon className="h-4 w-4 flex-shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-6 py-4 border-t border-card-border space-y-0.5">
        <div className="font-mono text-muted-foreground text-xs">
          XAUUSD · backtest only
        </div>
        {health?.version && (
          <div className="font-mono text-muted-foreground/50 text-xs">
            v{health.version}
          </div>
        )}
      </div>
    </aside>
  )
}
