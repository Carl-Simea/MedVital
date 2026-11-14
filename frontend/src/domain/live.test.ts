import { describe, expect, it } from 'vitest'
import { ageSeconds, formatAge, formatValue, indicatorLabel, rowsByDomain, STALE_AFTER_SECONDS, type LiveResponse } from './live'

const SERVER = '2030-01-01T12:00:10Z'

const live: LiveResponse = {
  server_time: SERVER,
  totals: { observations_stored: 4, rejected: 0 },
  notice: 'synthetic',
  devices: [
    {
      device_id: 'DEV-2',
      crew_id: 'CREW-002',
      last_seen: '2030-01-01T12:00:09Z',
      readings: [
        { domain: 'cardiovascular', indicator: 'heart_rate', metric: 'cardiovascular.heart_rate', value: 71.5, unit: '{beats}/min', observed_at: '2030-01-01T12:00:09Z', quality: 'valid', data_origin: 'simulated', source: 'simulated_sensor' },
      ],
    },
    {
      device_id: 'DEV-1',
      crew_id: 'CREW-001',
      last_seen: '2030-01-01T11:59:00Z',
      readings: [
        { domain: 'cardiovascular', indicator: 'heart_rate', metric: 'cardiovascular.heart_rate', value: 60, unit: '{beats}/min', observed_at: '2030-01-01T11:59:00Z', quality: 'suspect', data_origin: 'simulated', source: 'simulated_sensor' },
        { domain: 'radiation', indicator: 'dose_rate', metric: 'radiation.dose_rate', value: 10, unit: 'uGy/h', observed_at: '2030-01-01T12:00:09Z', quality: 'valid', data_origin: 'simulated', source: 'simulated_sensor' },
      ],
    },
  ],
}

describe('live helpers', () => {
  it('measures age against the gateway clock and never goes negative', () => {
    expect(ageSeconds('2030-01-01T12:00:00Z', SERVER)).toBe(10)
    expect(ageSeconds('2030-01-01T12:00:30Z', SERVER)).toBe(0)
  })

  it('groups readings into the four domains, sorted by indicator then device', () => {
    const rows = rowsByDomain(live)
    expect(Object.keys(rows).sort()).toEqual(['behavioral', 'bone', 'cardiovascular', 'radiation'])
    expect(rows.cardiovascular.map((r) => r.device_id)).toEqual(['DEV-1', 'DEV-2'])
    expect(rows.radiation).toHaveLength(1)
    expect(rows.bone).toEqual([])
  })

  it('flags stale readings and keeps quality and origin intact', () => {
    const [old, fresh] = rowsByDomain(live).cardiovascular
    expect(old?.stale).toBe(true)
    expect(old?.ageSeconds).toBeGreaterThan(STALE_AFTER_SECONDS)
    expect(old?.reading.quality).toBe('suspect')
    expect(fresh?.stale).toBe(false)
    expect(fresh?.reading.data_origin).toBe('simulated')
  })

  it('formats values, ages and labels', () => {
    expect(formatValue(71.5)).toBe('71.5')
    expect(formatValue(1234.567)).toBe('1,234.57')
    expect(formatAge(0.4)).toBe('just now')
    expect(formatAge(12)).toBe('12 s ago')
    expect(formatAge(300)).toBe('5 min ago')
    expect(indicatorLabel('dose_rate')).toBe('dose rate')
  })
})
