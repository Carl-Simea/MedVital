import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'
import { ProvenanceBadge } from './components/ProvenanceBadge'

describe('App shell', () => {
  it('renders the four independent health modules', () => {
    render(<App />)
    const modules = within(screen.getByRole('region', { name: 'Health modules' }))
    for (const name of ['Radiation', 'Bone health', 'Cardiovascular health', 'Behavioral health']) {
      expect(modules.getByRole('heading', { name })).toBeInTheDocument()
    }
  })

  it('states that it gives no diagnosis and applies no clinical thresholds', () => {
    render(<App />)
    expect(screen.getByRole('note')).toHaveTextContent(/no diagnosis/i)
    expect(screen.getByRole('note')).toHaveTextContent(/no clinical thresholds/i)
  })

  it('shows a legend for all three data origins', () => {
    render(<App />)
    const legend = within(screen.getByRole('region', { name: 'Data origin legend' }))
    for (const label of ['Simulated', 'Measured', 'Modeled']) expect(legend.getByText(label)).toBeInTheDocument()
  })
})

describe('ProvenanceBadge', () => {
  it('labels origin in text and exposes it as data-origin', () => {
    render(<ProvenanceBadge origin="modeled" />)
    expect(screen.getByText('Modeled')).toHaveAttribute('data-origin', 'modeled')
  })
})
