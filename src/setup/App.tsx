import { useState, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import '../index.css'

declare global {
  interface Window {
    sidecar: { port: string }
    electron: {
      setupComplete: (data: SetupData) => void
      getConfig: () => Promise<SetupData | null>
      onSetupError: (cb: (error: string) => void) => void
    }
  }
}

interface SetupData {
  riotApiKey: string
  geminiApiKey: string
  summonerName: string
  tagLine: string
  region: string
}

const REGIONS = ['NA1', 'EUW1', 'EUN1', 'KR', 'BR1', 'LA1', 'LA2', 'OC1', 'TR1', 'JP1']

function SetupApp() {
  const [riotApiKey, setRiotApiKey] = useState('')
  const [geminiApiKey, setGeminiApiKey] = useState('')
  const [summonerName, setSummonerName] = useState('')
  const [tagLine, setTagLine] = useState('')
  const [region, setRegion] = useState('NA1')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    window.electron.getConfig().then(config => {
      if (!config) return
      setRiotApiKey(config.riotApiKey)
      setGeminiApiKey(config.geminiApiKey)
      setSummonerName(config.summonerName)
      setTagLine(config.tagLine)
      setRegion(config.region)
    })
    window.electron.onSetupError(err => {
      setError(err)
      setLoading(false)
    })
  }, [])

  const submit = () => {
    if (!riotApiKey.trim() || !geminiApiKey.trim() || !summonerName.trim() || !tagLine.trim()) return
    setLoading(true)
    setError('')
    window.electron.setupComplete({
      riotApiKey: riotApiKey.trim(),
      geminiApiKey: geminiApiKey.trim(),
      summonerName: summonerName.trim(),
      tagLine: tagLine.trim(),
      region,
    })
  }

  const canSubmit = !loading && riotApiKey.trim() && geminiApiKey.trim() && summonerName.trim() && tagLine.trim()

  return (
    <div className="bg-[#1a1a2e] min-h-screen flex flex-col items-center justify-center text-white font-sans px-8">
      <h1 className="text-xl font-bold mb-1">Climb Setup</h1>
      <p className="text-gray-400 text-sm mb-6 text-center">Enter your API keys and Riot ID to get started.</p>

      <div className="w-full max-w-sm space-y-4">
        <div>
          <label className="text-gray-500 text-[10px] uppercase tracking-wide mb-1 block">Riot API Key</label>
          <input
            className="w-full bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none placeholder-gray-500"
            placeholder="RGAPI-..."
            value={riotApiKey}
            onChange={e => setRiotApiKey(e.target.value)}
          />
        </div>

        <div>
          <label className="text-gray-500 text-[10px] uppercase tracking-wide mb-1 block">Gemini API Key</label>
          <input
            className="w-full bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none placeholder-gray-500"
            placeholder="AIza..."
            value={geminiApiKey}
            onChange={e => setGeminiApiKey(e.target.value)}
          />
        </div>

        <div>
          <label className="text-gray-500 text-[10px] uppercase tracking-wide mb-1 block">Riot ID</label>
          <div className="flex gap-2">
            <input
              className="flex-1 bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none placeholder-gray-500"
              placeholder="Game Name"
              value={summonerName}
              onChange={e => setSummonerName(e.target.value)}
            />
            <span className="text-gray-500 self-center">#</span>
            <input
              className="w-20 bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none placeholder-gray-500"
              placeholder="TAG"
              value={tagLine}
              onChange={e => setTagLine(e.target.value)}
            />
          </div>
        </div>

        <select
          className="w-full bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none"
          value={region}
          onChange={e => setRegion(e.target.value)}
        >
          {REGIONS.map(r => <option key={r} value={r}>{r}</option>)}
        </select>

        {error && <p className="text-red-400 text-xs">{error}</p>}

        <button
          onClick={submit}
          disabled={!canSubmit}
          className="w-full py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm rounded-xl transition-colors"
        >
          {loading ? 'Connecting...' : 'Get Started'}
        </button>
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<SetupApp />)
