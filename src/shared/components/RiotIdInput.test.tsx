import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { RiotIdInput } from './RiotIdInput'

describe('RiotIdInput', () => {
  it('renders both fields with the passed values', () => {
    render(
      <RiotIdInput
        gameName="RoShet"
        tagLine="NA1"
        onGameNameChange={() => {}}
        onTagLineChange={() => {}}
      />,
    )
    expect(screen.getByPlaceholderText('Game Name')).toHaveValue('RoShet')
    expect(screen.getByPlaceholderText('TAG')).toHaveValue('NA1')
  })

  it('fires onGameNameChange when the game name changes', () => {
    const onGameNameChange = vi.fn()
    render(
      <RiotIdInput gameName="" tagLine="" onGameNameChange={onGameNameChange} onTagLineChange={() => {}} />,
    )
    fireEvent.change(screen.getByPlaceholderText('Game Name'), { target: { value: 'Faker' } })
    expect(onGameNameChange).toHaveBeenCalledWith('Faker')
  })

  it('fires onTagLineChange when the tag changes', () => {
    const onTagLineChange = vi.fn()
    render(
      <RiotIdInput gameName="" tagLine="" onGameNameChange={() => {}} onTagLineChange={onTagLineChange} />,
    )
    fireEvent.change(screen.getByPlaceholderText('TAG'), { target: { value: 'KR1' } })
    expect(onTagLineChange).toHaveBeenCalledWith('KR1')
  })
})
