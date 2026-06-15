import { useState } from 'react'
import { sidecarUrl } from '../shared/api'

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
        <div className="flex gap-2">
          <input
            className="flex-1 bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none placeholder-gray-500"
            placeholder="Game Name"
            value={gameName}
            onChange={e => setGameName(e.target.value)}
          />
          <span className="text-gray-500 self-center">#</span>
          <input
            className="w-20 bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none placeholder-gray-500"
            placeholder="TAG"
            value={tagLine}
            onChange={e => setTagLine(e.target.value)}
          />
        </div>

        <select
          className="w-full bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none [color-scheme:dark]"
          value={region}
          onChange={e => setRegion(e.target.value)}
        >
          {['NA1','EUW1','EUNE1','KR','BR1','LAN','LAS','OC1','TR1','RU','JP1'].map(r => (
            <option key={r} value={r} className="bg-[#1a1a2e] text-white">{r}</option>
          ))}
        </select>

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
