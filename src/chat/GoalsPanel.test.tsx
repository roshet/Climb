import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { GoalsPanel } from './GoalsPanel'
import * as api from '../shared/api'
import type { Goal, GoalMetricInfo, BenchmarkResponse } from '../shared/types'

vi.mock('../shared/api')

const benchmarks: BenchmarkResponse = {
  user_tier: 'PLATINUM',
  target_tier: 'DIAMOND',
  role: 'MIDDLE',
  status: 'ready',
  updated_at: '2026-06-24T00:00:00Z',
  metrics: [
    { metric_key: 'deaths', label: 'Deaths', comparison: 'lte', your_avg: 5.4, tier_avg: 4.1, sample_count: 1830 },
    { metric_key: 'cs', label: 'CS', comparison: 'gte', your_avg: 180, tier_avg: 220, sample_count: 1830 },
  ],
}

const metrics: GoalMetricInfo[] = [
  { key: 'deaths', label: 'Deaths', comparison: 'lte', is_float: false },
  { key: 'cs', label: 'CS', comparison: 'gte', is_float: false },
]

const goal: Goal = {
  id: 1,
  metric: 'deaths',
  label: 'Deaths',
  comparison: 'lte',
  target: 4,
  streak: 3,
  history: [true, false, true],
  last_game_met: true,
  games_evaluated: 5,
}

beforeEach(() => {
  vi.mocked(api.getJson).mockImplementation(async (path: string) => {
    if (path === '/goals') return [goal] as unknown as never
    if (path === '/goals/metrics') return metrics as unknown as never
    if (path === '/benchmarks') return benchmarks as unknown as never
    return null
  })
  vi.mocked(api.postJson).mockResolvedValue(goal as unknown as never)
  vi.mocked(api.delJson).mockResolvedValue({ ok: true } as unknown as never)
})

describe('GoalsPanel', () => {
  it('renders a returned goal with its streak', async () => {
    render(<GoalsPanel />)
    expect(await screen.findByTestId('streak-1')).toBeInTheDocument()
    expect(screen.getByTestId('streak-1')).toHaveTextContent('3')
  })

  it('builds the metric dropdown from the catalog', async () => {
    render(<GoalsPanel />)
    expect(await screen.findByRole('option', { name: 'Deaths' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'CS' })).toBeInTheDocument()
  })

  it('posts a new goal when Add is clicked', async () => {
    render(<GoalsPanel />)
    await screen.findByRole('option', { name: 'CS' })
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'cs' } })
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '70' } })
    fireEvent.click(screen.getByRole('button', { name: /add/i }))
    await waitFor(() =>
      expect(api.postJson).toHaveBeenCalledWith('/goals', { metric: 'cs', target: 70 }),
    )
  })

  it('deletes a goal when its delete button is clicked', async () => {
    render(<GoalsPanel />)
    fireEvent.click(await screen.findByRole('button', { name: /delete goal/i }))
    await waitFor(() => expect(api.delJson).toHaveBeenCalledWith('/goals/1'))
  })

  it('renders the benchmark block against the target tier', async () => {
    render(<GoalsPanel />)
    expect(await screen.findByText(/Benchmarks vs Diamond/i)).toBeInTheDocument()
    expect(screen.getByTestId('bench-deaths')).toHaveTextContent('5.4')
    expect(screen.getByTestId('bench-deaths')).toHaveTextContent('4.1')
  })

  it('shows a building state while harvesting', async () => {
    vi.mocked(api.getJson).mockImplementation(async (path: string) => {
      if (path === '/goals') return [] as unknown as never
      if (path === '/goals/metrics') return metrics as unknown as never
      if (path === '/benchmarks') return { ...benchmarks, status: 'harvesting', metrics: [] } as unknown as never
      return null
    })
    render(<GoalsPanel />)
    expect(await screen.findByText(/building your benchmarks/i)).toBeInTheDocument()
  })
})
