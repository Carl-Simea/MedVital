import { describe, expect, it } from 'vitest'
import { makeObservation } from '../test/factories'
import { MODULES } from './modules'
import { MODULE_IDS, validateObservation } from './observation'

const errorsOf = (input: unknown) => {
  const r = validateObservation(input)
  return r.ok ? [] : r.errors
}

describe('validateObservation', () => {
  it('accepts a valid simulated observation', () => {
    expect(validateObservation(makeObservation()).ok).toBe(true)
  })

  it('requires provenance', () => {
    const o: Record<string, unknown> = { ...makeObservation() }
    delete o.provenance
    expect(errorsOf(o)).toContain('provenance is required')
  })

  it('enforces origin-specific provenance rules', () => {
    const base = makeObservation()
    expect(errorsOf({ ...base, provenance: { data_origin: 'simulated', source: 's' } })).toContain(
      'simulated provenance requires generator_version and seed',
    )
    expect(errorsOf({ ...base, provenance: { data_origin: 'measured', source: 's' } })).toContain(
      'measured provenance requires source_ref',
    )
    expect(errorsOf({ ...base, provenance: { data_origin: 'modeled', source: 's' } })).toContain(
      'modeled provenance requires method',
    )
    expect(
      validateObservation({
        ...base,
        provenance: { data_origin: 'measured', source: 's', source_ref: 'test://x' },
      }).ok,
    ).toBe(true)
  })

  it('rejects non-finite values and metric/module mismatch', () => {
    expect(errorsOf(makeObservation({ value: Number.NaN }))).toContain('value must be a finite number')
    expect(errorsOf(makeObservation({ module: 'bone' }))).toContain('metric does not belong to module')
  })

  it('rejects timestamps without a UTC offset', () => {
    expect(errorsOf(makeObservation({ observed_at: '2030-01-01T00:00:00' }))[0]).toMatch(/observed_at/)
    expect(validateObservation(makeObservation({ observed_at: '2030-01-01T05:00:00+05:00' })).ok).toBe(true)
  })

  it('rejects a non-UUID id and self-supersede', () => {
    expect(errorsOf(makeObservation({ id: 'nope' }))).toContain('id must be a UUID')
    const o = makeObservation()
    expect(errorsOf({ ...o, supersedes: o.id })).toContain('supersedes must be a different observation UUID')
  })

  it('accepts unknown or known uncertainty and rejects invalid uncertainty', () => {
    expect(errorsOf(makeObservation())).toEqual([])
    expect(errorsOf({ ...makeObservation(), uncertainty: null })).toEqual([])
    expect(errorsOf({ ...makeObservation(), uncertainty: 0 })).toEqual([])
    expect(errorsOf({ ...makeObservation(), uncertainty: 0.4 })).toEqual([])
    for (const bad of [-1, Number.NaN, Number.POSITIVE_INFINITY, '0.4']) {
      expect(errorsOf({ ...makeObservation(), uncertainty: bad })).toContain(
        'uncertainty must be a finite number >= 0, or null when unknown',
      )
    }
  })

  it('rejects non-objects', () => {
    expect(errorsOf(null)).toEqual(['observation must be an object'])
  })
})

describe('module registry', () => {
  it('lists exactly the four modules', () => {
    expect(MODULES.map((m) => m.id).sort()).toEqual([...MODULE_IDS].sort())
    expect(MODULES).toHaveLength(4)
  })
})
