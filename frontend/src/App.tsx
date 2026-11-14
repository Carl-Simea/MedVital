import { LiveDashboard } from './components/LiveDashboard'
import { ProvenanceBadge } from './components/ProvenanceBadge'
import { SyncStatus } from './components/SyncStatus'
import { DATA_ORIGINS } from './domain/observation'

export default function App() {
  return (
    <div className="mx-auto max-w-6xl p-6 text-slate-900">
      <header className="mb-6 border-b border-slate-300 pb-4">
        <h1 className="text-2xl font-bold">MEDVITAL</h1>
        <p className="text-sm text-slate-600">
          Offline-first astronaut health observation platform — spacecraft gateway live view.
        </p>
        <div className="mt-3">
          <SyncStatus />
        </div>
      </header>

      <p role="note" className="mb-6 rounded border border-slate-300 bg-slate-50 p-3 text-sm">
        MEDVITAL presents descriptive statistics only. It is not a medical device, gives no diagnosis,
        and applies no clinical thresholds.
      </p>

      <section aria-label="Data origin legend" className="mb-6 flex flex-wrap items-center gap-2 text-sm">
        <span className="font-semibold">Data origin:</span>
        {DATA_ORIGINS.map((origin) => (
          <ProvenanceBadge key={origin} origin={origin} />
        ))}
      </section>

      <LiveDashboard />
    </div>
  )
}
