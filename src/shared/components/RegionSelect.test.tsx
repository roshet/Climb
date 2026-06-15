import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { RegionSelect } from './RegionSelect'

describe('RegionSelect', () => {
  const ALL = ['NA1', 'EUW1', 'EUNE1', 'KR', 'BR1', 'LAN', 'LAS', 'OC1', 'PH2', 'SG2', 'TH2', 'TW2', 'VN2', 'TR1', 'RU', 'JP1']

  it('renders all 16 region options matching the routing map keys', () => {
    render(<RegionSelect value="NA1" onChange={() => {}} />)
    for (const r of ALL) {
      expect(screen.getByRole('option', { name: r })).toBeInTheDocument()
    }
  })

  it('reflects the value prop as the selected option', () => {
    render(<RegionSelect value="KR" onChange={() => {}} />)
    expect(screen.getByRole('combobox')).toHaveValue('KR')
  })

  it('fires onChange with the selected region', () => {
    const onChange = vi.fn()
    render(<RegionSelect value="NA1" onChange={onChange} />)
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'EUNE1' } })
    expect(onChange).toHaveBeenCalledWith('EUNE1')
  })
})
