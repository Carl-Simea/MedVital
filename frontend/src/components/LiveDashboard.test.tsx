import { render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { LiveResponse } from '../domain/live'
import { LiveDashboard } from './LiveDashboard'

const payload: LiveResponse = {
  server_time: '2030-01-01T12:00:10Z',
  totals: { observations_stored: 7, rejected: 2 },
  notice: 'Live gateway view. Values labelled simulated are synthetic test signals, not astronaut data.',
  devices: [
    {
      device_id: 'MEDVITAL-WEARABLE-001',
      crew_id: 'CREW-001',
      last_seen: '2030-01-01T12:00:09Z',
      readings: [
        { domain: 'cardiovascular', indicator: 'heart_rate', metric: 'cardiovascular.heart_rate', value: 61.25, unit: '{beats}/min', observed_at: '2030-01-01T12:00:09Z', quality: 'valid', data_origin: 'simulated', source: 'simulated_sensor' },
        { domain: 'radiation', indicator: 'dose_rate', metric: 'radiation.dose_rate', value: 10.1, unit: 'uGy/h', observed_at: '2030-01-01T11:59:00Z', quality: 'suspect', data_origin: 'simulated', source: 'simulated_sensor' },
      ],
    },
  ],
}

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 })

afterEach(() => vi.unstubAllGlobals())

describe('LiveDashboard', () => {
  it('shows live readings under their domain, labelled simulated, with quality and staleness', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ok(payload)))
    render(<LiveDashboard intervalMs={20} />)

    const cardio = await screen.findByRole('heading', { name: 'Cardiovascular health' })
    const card = cardio.closest('article') as HTMLElement
    expect(within(card).getByText('61.25')).toBeInTheDocument()
    expect(within(card).getByText('heart rate')).toBeInTheDocument()
    expect(within(card).getByText('Simulated')).toHaveAttribute('data-origin', 'simulated')

    const radiation = screen.getByRole('heading', { name: 'Radiation' }).closest('article') as HTMLElement
    expect(within(radiation).getByText(/suspect/)).toBeInTheDocument()
    expect(within(radiation).getByText(/STALE/)).toBeInTheDocument()

    expect(screen.getByText('Gateway connected')).toBeInTheDocument()
    expect(screen.getByText('Observations stored: 7')).toBeInTheDocument()
    expect(screen.getByText('Rejected (audited): 2')).toBeInTheDocument()
    expect(screen.getByTestId('synthetic-notice')).toHaveTextContent(/not astronaut data/)
  })

  it('shows domains with no readings as empty rather than inventing data', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ok(payload)))
    render(<LiveDashboard intervalMs={20} />)
    const bone = (await screen.findByRole('heading', { name: 'Bone health' })).closest('article') as HTMLElement
    await waitFor(() => expect(within(bone).getByText('No readings yet.')).toBeInTheDocument())
  })

  it('when the gateway goes away, keeps the last data on screen and says it is unreachable', async () => {
    let calls = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        calls += 1
        if (calls === 1) return ok(payload)
        throw new TypeError('Failed to fetch')
      }),
    )
    render(<LiveDashboard intervalMs={20} />)
    await screen.findByText('61.25')
    await waitFor(() => expect(screen.getByText(/Gateway unreachable/)).toBeInTheDocument())
    expect(screen.getByText('61.25')).toBeInTheDocument() // last good data is still shown
  })

  it('before the first response, shows a waiting state', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => undefined)))
    render(<LiveDashboard intervalMs={20} />)
    expect(screen.getAllByText('Waiting for the gateway…')).toHaveLength(4)
  })
})
