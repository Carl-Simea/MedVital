import { MODULES } from '../domain/modules'
import { formatAge, formatValue, indicatorLabel, rowsByDomain } from '../domain/live'
import { ProvenanceBadge } from './ProvenanceBadge'
import { useLive } from './useLive'

/** Basic live view of what the spacecraft gateway is receiving. Presentation only. */
export function LiveDashboard({ intervalMs = 1000 }: { intervalMs?: number }) {
  const { live, error } = useLive(intervalMs)
  const rows = live ? rowsByDomain(live) : null

  return (
    <div>
      <div role="status" aria-label="Gateway link" className="mb-4 flex flex-wrap items-center gap-4 text-sm">
        <span className={error ? 'font-semibold text-red-700' : 'font-semibold text-emerald-700'}>
          {error ? `Gateway unreachable (${error}) — showing last data` : 'Gateway connected'}
        </span>
        {live && (
          <>
            <span>Devices: {live.devices.length}</span>
            <span>Observations stored: {live.totals.observations_stored}</span>
            <span>Rejected (audited): {live.totals.rejected}</span>
          </>
        )}
      </div>

      {live && (
        <p data-testid="synthetic-notice" className="mb-4 rounded border border-amber-500 bg-amber-50 p-2 text-sm">
          {live.notice}
        </p>
      )}

      <section aria-label="Health modules" className="grid gap-4 md:grid-cols-2">
        {MODULES.map((m) => {
          const domainRows = rows?.[m.id] ?? []
          return (
            <article key={m.id} data-module={m.id} className="rounded border border-slate-300 p-4">
              <h2 className="text-lg font-semibold">{m.name}</h2>
              <p className="mb-2 text-xs text-slate-500">{m.description}</p>
              {domainRows.length === 0 ? (
                <p className="text-sm text-slate-500">{live ? 'No readings yet.' : 'Waiting for the gateway…'}</p>
              ) : (
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="text-xs text-slate-500">
                      <th className="py-1 pr-2">Crew / device</th>
                      <th className="py-1 pr-2">Indicator</th>
                      <th className="py-1 pr-2 text-right">Value</th>
                      <th className="py-1 pr-2">Origin</th>
                      <th className="py-1">Quality · age</th>
                    </tr>
                  </thead>
                  <tbody>
                    {domainRows.map((r) => (
                      <tr key={`${r.device_id}|${r.reading.metric}`} className={r.stale ? 'opacity-50' : ''}>
                        <td className="py-1 pr-2">
                          {r.crew_id}
                          <span className="block text-xs text-slate-500">{r.device_id}</span>
                        </td>
                        <td className="py-1 pr-2">{indicatorLabel(r.reading.indicator)}</td>
                        <td className="py-1 pr-2 text-right font-mono">
                          {formatValue(r.reading.value)} <span className="text-xs text-slate-500">{r.reading.unit}</span>
                        </td>
                        <td className="py-1 pr-2">
                          <ProvenanceBadge origin={r.reading.data_origin} />
                        </td>
                        <td className="py-1 text-xs">
                          {r.reading.quality}
                          {' · '}
                          {r.stale ? `STALE ${formatAge(r.ageSeconds)}` : formatAge(r.ageSeconds)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </article>
          )
        })}
      </section>
    </div>
  )
}
