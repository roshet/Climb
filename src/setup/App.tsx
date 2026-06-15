import { useState, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import '../index.css'
import { initRendererLogForwarding } from '../shared/log'
import { RegionSelect } from '../shared/components/RegionSelect'
import { RiotIdInput } from '../shared/components/RiotIdInput'

function SetupApp() {
  const [riotApiKey, setRiotApiKey] = useState('')
  const [geminiApiKey, setGeminiApiKey] = useState('')
  const [summonerName, setSummonerName] = useState('')
  const [tagLine, setTagLine] = useState('')
  const [region, setRegion] = useState('NA1')
  const [editMode, setEditMode] = useState(false)
  const [showKeys, setShowKeys] = useState(false)
  const [loading, setLoading] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    window.electron.getConfig().then(config => {
      if (!config) return
      // Existing config means this window is acting as Settings, not first-run setup.
      setEditMode(true)
      setRiotApiKey(config.riotApiKey)
      setGeminiApiKey(config.geminiApiKey)
      setSummonerName(config.summonerName)
      setTagLine(config.tagLine)
      setRegion(config.region)
    })
    window.electron.onSetupError(err => {
      setError(err)
      setLoading(false)
      setSaved(false)
    })
    window.electron.onSetupSaved(() => {
      setLoading(false)
      setSaved(true)
    })
  }, [])

  const dirty = () => {
    setError('')
    setSaved(false)
  }

  const submit = () => {
    if (!riotApiKey.trim() || !geminiApiKey.trim() || !summonerName.trim() || !tagLine.trim()) return
    setLoading(true)
    setError('')
    setSaved(false)
    window.electron.setupComplete({
      riotApiKey: riotApiKey.trim(),
      geminiApiKey: geminiApiKey.trim(),
      summonerName: summonerName.trim(),
      tagLine: tagLine.trim(),
      region,
    })
  }

  const canSubmit = !loading && riotApiKey.trim() && geminiApiKey.trim() && summonerName.trim() && tagLine.trim()
  const keyType = showKeys ? 'text' : 'password'

  return (
    <div className="bg-[#1a1a2e] min-h-screen flex flex-col items-center justify-center text-white font-sans px-8">
      <h1 className="text-xl font-bold mb-1">{editMode ? 'Settings' : 'Climb Setup'}</h1>
      <p className="text-gray-400 text-sm mb-6 text-center">
        {editMode
          ? 'Update your API keys and Riot ID. Saving restarts the analyst.'
          : 'Enter your API keys and Riot ID to get started.'}
      </p>

      <div className="w-full max-w-sm space-y-4">
        <div>
          <div className="flex justify-between items-center mb-1">
            <label className="text-gray-500 text-[10px] uppercase tracking-wide block">Riot API Key</label>
            <button
              type="button"
              onClick={() => setShowKeys(s => !s)}
              className="text-gray-500 hover:text-gray-300 text-[10px] uppercase tracking-wide"
            >
              {showKeys ? 'Hide' : 'Show'}
            </button>
          </div>
          <input
            type={keyType}
            className="w-full bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none placeholder-gray-500"
            placeholder="RGAPI-..."
            value={riotApiKey}
            onChange={e => { setRiotApiKey(e.target.value); dirty() }}
          />
        </div>

        <div>
          <label className="text-gray-500 text-[10px] uppercase tracking-wide mb-1 block">Gemini API Key</label>
          <input
            type={keyType}
            className="w-full bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none placeholder-gray-500"
            placeholder="AIza..."
            value={geminiApiKey}
            onChange={e => { setGeminiApiKey(e.target.value); dirty() }}
          />
        </div>

        <div>
          <label className="text-gray-500 text-[10px] uppercase tracking-wide mb-1 block">Riot ID</label>
          <RiotIdInput
            gameName={summonerName}
            tagLine={tagLine}
            onGameNameChange={v => { setSummonerName(v); dirty() }}
            onTagLineChange={v => { setTagLine(v); dirty() }}
          />
        </div>

        <RegionSelect value={region} onChange={v => { setRegion(v); dirty() }} />

        {error && <p className="text-red-400 text-xs">{error}</p>}
        {saved && !error && <p className="text-green-400 text-xs">Saved ✓</p>}

        <button
          onClick={submit}
          disabled={!canSubmit}
          className="w-full py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm rounded-xl transition-colors"
        >
          {loading
            ? (editMode ? 'Saving...' : 'Connecting...')
            : (editMode ? 'Save' : 'Get Started')}
        </button>
      </div>
    </div>
  )
}

initRendererLogForwarding()
createRoot(document.getElementById('root')!).render(<SetupApp />)
