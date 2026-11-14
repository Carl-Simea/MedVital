/**
 * Live gateway view (GET /api/v1/live) — types and pure helpers. No React, no fetching.
 * Mirrors backend/medvital/live.py; the backend is authoritative.
 */
import type { DataOrigin, ModuleId } from './observation'

export type Quality = 'valid' | 'suspect' | 'invalid'

export interface LiveReading {
  domain: ModuleId
  indicator: string
  metric: string
  value: number
  unit: string
  observed_at: string
  quality: Quality
  data_origin: DataOrigin
  source: string
}

export interface LiveDevice {
  device_id: string
  crew_id: string
  last_seen: string
  readings: LiveReading[]
}

export interface LiveResponse {
  server_time: string
  totals: { observations_stored: number; rejected: number }
  devices: LiveDevice[]
  notice: string
}

/** Readings older than this (by the gateway's clock) are shown as stale. Engineering default. */
export const STALE_AFTER_SECONDS = 10

export interface DomainRow {
  device_id: string
  crew_id: string
  reading: LiveReading
  ageSeconds: number
  stale: boolean
}

/** Age is measured against the gateway's clock (server_time), never the browser's, so laptops with
 *  drifting clocks cannot make fresh data look stale or vice versa. */
export function ageSeconds(observedAt: string, serverTime: string): number {
  return Math.max(0, (Date.parse(serverTime) - Date.parse(observedAt)) / 1000)
}

export function rowsByDomain(live: LiveResponse): Record<ModuleId, DomainRow[]> {
  const out: Record<ModuleId, DomainRow[]> = { radiation: [], bone: [], cardiovascular: [], behavioral: [] }
  for (const device of live.devices) {
    for (const reading of device.readings) {
      const age = ageSeconds(reading.observed_at, live.server_time)
      out[reading.domain].push({
        device_id: device.device_id,
        crew_id: device.crew_id,
        reading,
        ageSeconds: age,
        stale: age > STALE_AFTER_SECONDS,
      })
    }
  }
  for (const rows of Object.values(out)) {
    rows.sort((a, b) => a.reading.indicator.localeCompare(b.reading.indicator) || a.device_id.localeCompare(b.device_id))
  }
  return out
}

export function formatAge(seconds: number): string {
  if (seconds < 1.5) return 'just now'
  if (seconds < 90) return `${Math.round(seconds)} s ago`
  return `${Math.round(seconds / 60)} min ago`
}

export function formatValue(value: number): string {
  return value.toLocaleString('en-US', { maximumFractionDigits: 2 })
}

export function indicatorLabel(indicator: string): string {
  return indicator.replace(/_/g, ' ')
}
