import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MomentCard } from './MomentCard'

describe('MomentCard', () => {
  it('renders the description, formatted type, and timestamp', () => {
    render(
      <MomentCard
        timestampSecs={323}
        momentType="lane_death"
        description="You died to a gank."
        counterfactual=""
        goldImpact={-300}
      />,
    )
    expect(screen.getByText('You died to a gank.')).toBeInTheDocument()
    expect(screen.getByText('LANE DEATH')).toBeInTheDocument()
    expect(screen.getByText('5:23')).toBeInTheDocument()
  })

  it('shows the gold loss for a negative impact', () => {
    render(
      <MomentCard
        timestampSecs={0}
        momentType="death"
        description="x"
        counterfactual=""
        goldImpact={-300}
      />,
    )
    expect(screen.getByText(/300g/)).toBeInTheDocument()
  })
})
