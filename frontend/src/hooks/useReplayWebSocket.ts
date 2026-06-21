import { useEffect, useRef, useCallback, useState, useLayoutEffect } from 'react'
import { WS_BASE, type ReplayFrame } from '@/lib/api'

export type ReplayAction =
  | { action: 'play'; speed?: number }
  | { action: 'pause' }
  | { action: 'step' }
  | { action: 'step_back' }
  | { action: 'seek'; bar_index: number }
  | { action: 'speed'; speed: number }

export type WsStatus = 'connecting' | 'open' | 'closed' | 'error'

interface UseReplayWebSocketOptions {
  sessionId: string | null
  onFrame: (frame: ReplayFrame) => void
  onDone?: () => void
  onError?: (err: Event) => void
}

const MAX_RECONNECT_ATTEMPTS = 3

export function useReplayWebSocket({
  sessionId,
  onFrame,
  onDone,
  onError,
}: UseReplayWebSocketOptions) {
  const [status, setStatus] = useState<WsStatus>('connecting')
  const wsRef = useRef<WebSocket | null>(null)

  // Ref-forwarding pattern: always call the latest version of each callback
  // without adding them to the useEffect dependency array (avoids reconnect on
  // every render where the parent re-creates arrow functions).
  const onFrameRef = useRef(onFrame)
  const onDoneRef  = useRef(onDone)
  const onErrorRef = useRef(onError)
  useLayoutEffect(() => { onFrameRef.current = onFrame }, [onFrame])
  useLayoutEffect(() => { onDoneRef.current  = onDone  }, [onDone])
  useLayoutEffect(() => { onErrorRef.current = onError }, [onError])

  const send = useCallback((action: ReplayAction) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(action))
    }
  }, [])

  useEffect(() => {
    if (!sessionId) return

    let attempts = 0
    let intentionalClose = false   // true when unmount or 'done' received
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null

    function connect() {
      setStatus('connecting')
      const ws = new WebSocket(`${WS_BASE}/ws/replay/${sessionId}`)
      wsRef.current = ws

      ws.onopen = () => {
        attempts = 0
        setStatus('open')
      }

      ws.onmessage = (ev: MessageEvent) => {
        try {
          const msg = JSON.parse(ev.data as string) as { type: string } & ReplayFrame
          if (msg.type === 'frame') {
            onFrameRef.current(msg)
          } else if (msg.type === 'done') {
            intentionalClose = true   // normal end — don't reconnect
            onDoneRef.current?.()
          } else if (msg.type === 'error') {
            intentionalClose = true
            setStatus('error')
          }
        } catch {
          // ignore malformed messages
        }
      }

      ws.onerror = (ev) => {
        setStatus('error')
        onErrorRef.current?.(ev)
      }

      ws.onclose = () => {
        wsRef.current = null
        if (intentionalClose || attempts >= MAX_RECONNECT_ATTEMPTS) {
          setStatus('closed')
          return
        }
        // Exponential backoff: 1 s, 2 s, 4 s
        const delay = Math.pow(2, attempts) * 1000
        attempts++
        reconnectTimer = setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      intentionalClose = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [sessionId])

  return { send, status }
}
