import * as React from 'react'
import { cn } from '@/lib/utils'

interface TerminalCardProps extends React.HTMLAttributes<HTMLDivElement> {
  title?: string
  headerRight?: React.ReactNode
}

export function TerminalCard({
  title,
  headerRight,
  children,
  className,
  ...props
}: TerminalCardProps) {
  return (
    <div
      className={cn(
        'rounded-lg border border-card-border bg-background overflow-hidden',
        className,
      )}
      {...props}
    >
      {(title || headerRight) && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-card-border bg-secondary/30">
          {title && (
            <span className="font-mono text-xs text-accent font-semibold uppercase tracking-wider">
              {title}
            </span>
          )}
          {headerRight && <div className="flex items-center gap-2">{headerRight}</div>}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  )
}
