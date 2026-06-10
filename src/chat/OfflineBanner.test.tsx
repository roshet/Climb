import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { OfflineBanner } from './OfflineBanner'

describe('OfflineBanner', () => {
  it('renders nothing when online', () => {
    const { container } = render(<OfflineBanner offline={false} />)
    expect(container).toBeEmptyDOMElement()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows the reconnecting alert when offline', () => {
    render(<OfflineBanner offline={true} />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText(/reconnecting/i)).toBeInTheDocument()
  })
})
