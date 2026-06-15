import { useState } from 'react'
import { sidecarUrl } from '../shared/api'
import { RegionSelect } from '../shared/components/RegionSelect'
import { RiotIdInput } from '../shared/components/RiotIdInput'

interface SetupProps {
  onComplete: () => void
}

export function Setup({ onComplete }: SetupProps) {
  const [gameName, setGameName] = useState('')
  const [tagLine, setTagLine] = useState('')
  const [region, setRegion] = useState('NA1')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    if (!gameName.trim() || !tagLine.trim()) return
    setLoading(true)
    setError('')
    try {
      const res = await fetch(sidecarUrl('/setup'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ summoner_name: gameName.trim(), tag_line: tagLine.trim(), region }),
      })
      if (!res.ok) {
        const err = await res.json() as { detail: string }
        setError(err.detail || 'Setup failed.')
        return
      }
      onComplete()
    } catch {
      setError('Could not connect to sidecar.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-[#1a1a2e] h-screen flex flex-col items-center justify-center text-white font-sans px-8">
      <h1 className="text-xl font-bold mb-2">LoL Analyst Setup</h1>
      <p className="text-gray-400 text-sm mb-6 text-center">Enter your Riot ID to get started. This is a one-time setup.</p>

      <div className="w-full max-w-sm space-y-3">
        <RiotIdInput
          gameName={gameName}
          tagLine={tagLine}
          onGameNameChange={setGameName}
          onTagLineChange={setTagLine}
        />

        <RegionSelect value={region} onChange={setRegion} />

        {error && <p className="text-red-400 text-xs">{error}</p>}

        <button
          onClick={submit}
          disabled={loading || !gameName.trim() || !tagLine.trim()}
          className="w-full py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm rounded-xl transition-colors"
        >
          {loading ? 'Connecting...' : 'Get Started'}
        </button>
      </div>
    </div>
  )
}
