import { useCallback, useEffect, useState } from "react";
import { createApiClient, type ApiClient } from "./api/client";
import { ModuleCard } from "./components/ModuleCard";
import { ProvenanceBadge } from "./components/ProvenanceBadge";
import { DATA_ORIGINS, MODULE_IDS, type ModuleId } from "./domain/types";
import { ORIGIN_LABELS } from "./domain/presentation";
import { useOnlineStatus } from "./hooks/useOnlineStatus";
import { ObservationStore } from "./offline/store";
import { syncOnce } from "./offline/sync";

interface AppProps {
  openStore?: () => Promise<ObservationStore>;
  api?: ApiClient;
}

// Module-level defaults keep prop identities stable, so the effect below runs once.
const defaultApi = createApiClient();
const defaultOpenStore = () => ObservationStore.open();

export default function App({ openStore = defaultOpenStore, api = defaultApi }: AppProps) {
  const online = useOnlineStatus();
  const [store, setStore] = useState<ObservationStore | null>(null);
  const [counts, setCounts] = useState<Record<ModuleId, number>>({
    radiation: 0,
    bone: 0,
    cardiovascular: 0,
    behavioral: 0,
  });
  const [pending, setPending] = useState(0);
  const [message, setMessage] = useState("");

  const refresh = useCallback(async (s: ObservationStore) => {
    const all = await s.list();
    const next = { radiation: 0, bone: 0, cardiovascular: 0, behavioral: 0 };
    for (const o of all) next[o.module] += 1;
    setCounts(next);
    setPending((await s.outbox("pending")).length);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let opened: ObservationStore | null = null;
    openStore().then(async (s) => {
      if (cancelled) {
        s.close();
        return;
      }
      opened = s;
      setStore(s);
      await refresh(s);
    });
    return () => {
      cancelled = true;
      opened?.close();
    };
  }, [openStore, refresh]);

  async function handleSync() {
    if (!store) return;
    setMessage("Syncing...");
    try {
      const r = await syncOnce(store, api);
      setMessage(`Synced: ${r.pushed} sent, ${r.pulled} received, ${r.rejected} rejected.`);
      await refresh(store);
    } catch {
      setMessage("Could not reach the server. Your data is saved on this device.");
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white px-6 py-4">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <h1 className="text-xl font-bold tracking-tight">MEDVITAL</h1>
          <p
            role="status"
            data-testid="connectivity"
            className={online ? "text-sm text-emerald-700" : "text-sm text-amber-700"}
          >
            {online ? "Online" : "Offline: working from local data"}
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-6 px-6 py-6">
        <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-200">
          Research prototype. Not a medical device. No diagnosis is provided and no clinical
          thresholds are applied.
        </p>

        <section aria-label="Health modules" className="grid gap-4 sm:grid-cols-2">
          {MODULE_IDS.map((id) => (
            <ModuleCard key={id} module={id} count={counts[id]} />
          ))}
        </section>

        <section aria-label="Data provenance legend" className="space-y-2">
          <h2 className="text-sm font-semibold text-slate-700">How to read data labels</h2>
          <ul className="space-y-1 text-sm text-slate-600">
            {DATA_ORIGINS.map((origin) => (
              <li key={origin} className="flex items-center gap-2">
                <ProvenanceBadge origin={origin} />
                <span>{ORIGIN_LABELS[origin].description}</span>
              </li>
            ))}
          </ul>
        </section>

        <section aria-label="Synchronisation" className="flex items-center gap-4">
          <button
            type="button"
            onClick={handleSync}
            disabled={!store || !online}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
          >
            Sync now
          </button>
          <span className="text-sm text-slate-600" data-testid="pending">
            {pending} waiting to upload
          </span>
          <span className="text-sm text-slate-600" role="status">
            {message}
          </span>
        </section>
      </main>
    </div>
  );
}
