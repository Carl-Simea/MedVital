import { useEffect, useState } from 'react'
import { fetchLive } from '../api/live'
import type { LiveResponse } from '../domain/live'

export interface LiveState {
  live: LiveResponse | null
  /** null while healthy; message when the last poll failed (the previous data stays on screen). */
  error: string | null
}

/** Polls the gateway. On failure the last good data is kept and flagged, never cleared. */
export function useLive(intervalMs = 1000): LiveState {
  const [state, setState] = useState<LiveState>({ live: null, error: null })

  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined

    const poll = async () => {
      try {
        const live = await fetchLive('/api/v1', undefined, controller.signal)
        setState({ live, error: null })
      } catch (e) {
        if (controller.signal.aborted) return
        setState((prev) => ({ live: prev.live, error: e instanceof Error ? e.message : 'gateway unreachable' }))
      }
      if (!controller.signal.aborted) timer = setTimeout(poll, intervalMs)
    }
    void poll()

    return () => {
      controller.abort()
      if (timer) clearTimeout(timer)
    }
  }, [intervalMs])

  return state
}
