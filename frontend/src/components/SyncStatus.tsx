import { useCallback, useEffect, useState } from 'react'
import { HttpTransport } from '../api/client'
import { DB_NAME, openDb } from '../offline/db'
import { LocalStore } from '../offline/store'
import { syncOnce, type SyncReport } from '../offline/syncEngine'
import { useOnlineStatus } from '../offline/useOnlineStatus'

const transport = new HttpTransport()

/** Minimal offline/sync indicator. Not the dashboard — just proves the offline path end to end. */
export function SyncStatus({ dbName = DB_NAME }: { dbName?: string }) {
  const online = useOnlineStatus()
  const [store, setStore] = useState<LocalStore | null>(null)
  const [pending, setPending] = useState<number | null>(null)
  const [report, setReport] = useState<SyncReport | null>(null)
  const [busy, setBusy] = useState(false)
  const [storageError, setStorageError] = useState<string | null>(null)

  useEffect(() => {
    let opened: LocalStore | null = null
    let cancelled = false
    openDb(dbName)
      .then(async (db) => {
        opened = new LocalStore(db)
        if (cancelled) return opened.close()
        setStore(opened)
        setPending(await opened.pendingCount())
      })
      .catch((e: unknown) => setStorageError(e instanceof Error ? e.message : 'local storage unavailable'))
    return () => {
      cancelled = true
      opened?.close()
    }
  }, [dbName])

  const sync = useCallback(async () => {
    if (!store) return
    setBusy(true)
    try {
      setReport(await syncOnce(store, transport))
      setPending(await store.pendingCount())
    } finally {
      setBusy(false)
    }
  }, [store])

  return (
    <div className="flex flex-wrap items-center gap-3 text-sm" role="status">
      <span className={online ? 'text-emerald-700' : 'text-amber-700'}>{online ? 'Network: online' : 'Network: offline'}</span>
      <span>
        {storageError
          ? `Local storage unavailable: ${storageError}`
          : `Waiting to upload: ${pending ?? '…'}`}
      </span>
      <button
        type="button"
        onClick={sync}
        disabled={!store || busy || !online}
        className="rounded border border-slate-400 px-2 py-1 disabled:opacity-50"
      >
        {busy ? 'Syncing…' : 'Sync now'}
      </button>
      {report && report.outcome !== 'ok' && (
        <span className="text-amber-700">
          Sync {report.outcome === 'offline' ? 'could not reach the server' : 'failed'}; data is kept locally.
        </span>
      )}
    </div>
  )
}
