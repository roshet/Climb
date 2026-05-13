import { useState, useEffect, useCallback } from 'react'
import { createRoot } from 'react-dom/client'
import { MessageList } from './MessageList'
import { InputBar } from './InputBar'
import { Setup } from './Setup'
import { HistoryList } from './HistoryList'
import { GameDetail } from './GameDetail'
import { TrendChart } from './TrendChart'
import { FocusCard, FocusCardData } from './FocusCard'
import { MatchRow } from './types'
import '../index.css'

declare global {
  interface Window { sidecar: { port: string } }
}

interface Message {
  role: 'user' | 'assistant'
  content: string
}

interface Pattern {
  moment_type: string
  label: 'recurring_issue' | 'win_condition'
  games_seen: number
  total_games: number
  win_rate_with: number
  overall_win_rate: number
  summary: string
}

type Tab = 'chat' | 'history'

const SESSION_ID = `session-${Date.now()}`

const MOMENT_LABELS: Record<string, string> = {
  lane_death: 'Lane Deaths',
  cs_differential: 'CS Deficit',
  gold_differential: 'Gold Deficit',
  turret_plates_lost: 'Plates Lost',
  split_push_death: 'Split Push Deaths',
  enemy_roam_kill: 'Enemy Roams',
  low_vision: 'Low Vision',
  objective_missed: 'Missed Objectives',
  tower_lost: 'Towers Lost',
  death: 'Deaths',
  jungle_death: 'Jungle Deaths',
  invade_death: 'Invade Deaths',
  counter_ganked: 'Counter-Ganked',
  first_blood_assist: 'First Blood Assists',
  solo_kill: 'Solo Kills',
  objective_secured: 'Objectives Secured',
  gank_assist: 'Gank Assists',
  baron_secured: 'Baron Secured',
  dragon_stack: 'Dragon Stacks',
  roam_kill: 'Roam Kills',
  roam_assist: 'Roam Assists',
  ward_kill: 'Vision Control',
  bad_back_objective: 'Bad Backs (Objective)',
  bad_back_gold: 'Bad Backs (Low Gold)',
}

function buildSessionMessage(games: MatchRow[], isToday: boolean): string {
  const header = isToday
    ? `Summarize my session today (${games.length} game${games.length === 1 ? '' : 's'}):`
    : `I haven't played today. Here are my last ${games.length} games:`
  const lines = games.map((m, i) => {
    const mins = Math.round(m.duration_secs / 60)
    return `${i + 1}. ${m.champion} (${m.result === 'win' ? 'Win' : 'Loss'}, ${m.kda}, ${mins}min, ${m.gold_lost}g lost, ${m.moment_count} mistakes)`
  })
  return `${header}\n\n${lines.join('\n')}\n\nWhat patterns do you see? What went well and what should I focus on next session?`
}

function ChatApp() {
  const [isSetup, setIsSetup] = useState<boolean | null>(null)
  const [tab, setTab] = useState<Tab>('chat')
  const [selectedMatchId, setSelectedMatchId] = useState<string | null>(null)
  const [chatMatchId, setChatMatchId] = useState<string | null>(
    new URLSearchParams(window.location.search).get('matchId')
  )
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: "Hi! I'm your personal LoL analyst. Ask me anything about your games — patterns, mistakes, champion performance, or what to focus on to climb." }
  ])
  const [loading, setLoading] = useState(false)
  const [summarizing, setSummarizing] = useState(false)
  const [patterns, setPatterns] = useState<Pattern[]>([])
  const [matches, setMatches] = useState<MatchRow[]>([])
  const [matchesLoading, setMatchesLoading] = useState(true)
  const [matchesError, setMatchesError] = useState(false)
  const [focusCard, setFocusCard] = useState<FocusCardData | null>(null)

  const port = window.sidecar?.port ?? '8765'

  useEffect(() => {
    fetch(`http://localhost:${port}/player`)
      .then(r => {
        if (r.status === 404) { setIsSetup(false); return }
        if (r.ok)             { setIsSetup(true);  return }
        setIsSetup(null)
      })
      .catch(() => setIsSetup(null))
  }, [port])

  useEffect(() => {
    if (isSetup !== true) return
    if (tab !== 'chat') return
    fetch(`http://localhost:${port}/focus`)
      .then(r => r.ok ? r.json() : null)
      .then(data => setFocusCard(data as FocusCardData | null))
      .catch(() => {})
  }, [port, isSetup, tab])

  useEffect(() => {
    if (isSetup !== true) return
    fetch(`http://localhost:${port}/patterns`)
      .then(r => r.ok ? r.json() : { patterns: [] })
      .then((data: { patterns: Pattern[] }) => setPatterns(data.patterns))
      .catch(() => {})
  }, [port, isSetup])

  useEffect(() => {
    if (tab !== 'history' || !isSetup) return
    setMatchesLoading(true)
    setMatchesError(false)
    fetch(`http://localhost:${port}/matches?last_n=20`)
      .then(r => {
        if (!r.ok) { setMatchesError(true); setMatchesLoading(false); return }
        r.json()
          .then((data: unknown) => {
            if (Array.isArray(data)) setMatches((data as MatchRow[]).slice().reverse())
            else setMatchesError(true)
            setMatchesLoading(false)
          })
          .catch(() => { setMatchesError(true); setMatchesLoading(false) })
      })
      .catch(() => { setMatchesError(true); setMatchesLoading(false) })
  }, [port, tab, isSetup])

  const sendMessage = useCallback(async (text: string) => {
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setLoading(true)
    try {
      const res = await fetch(`http://localhost:${port}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: SESSION_ID, message: text, match_id: chatMatchId }),
      })
      if (!res.ok) throw new Error('sidecar error')
      const data = await res.json() as { response: string }
      setMessages(prev => [...prev, { role: 'assistant', content: data.response }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error connecting to analyst. Is the sidecar running?' }])
    } finally {
      setLoading(false)
    }
  }, [port, chatMatchId])

  const handleAskAboutGame = useCallback((matchId: string) => {
    setChatMatchId(matchId)
    setSelectedMatchId(null)
    setTab('chat')
  }, [])

  const handleTabChange = useCallback((newTab: Tab) => {
    setTab(newTab)
    if (newTab === 'history') setSelectedMatchId(null)
  }, [])

  const handleBack = useCallback(() => setSelectedMatchId(null), [])

  const handleSummarize = useCallback(async () => {
    setSummarizing(true)
    try {
      const res = await fetch(`http://localhost:${port}/matches?last_n=20`)
      if (!res.ok) return
      const data = await res.json() as unknown
      if (!Array.isArray(data)) return
      const all = (data as MatchRow[]).slice().reverse()
      const today = new Date()
      today.setHours(0, 0, 0, 0)
      const todayGames = all.filter(m => new Date(m.played_at) >= today)
      const games = todayGames.length > 0 ? todayGames : all.slice(-5)
      sendMessage(buildSessionMessage(games, todayGames.length > 0))
    } catch {
      // silently swallow fetch/parse errors
    } finally {
      setSummarizing(false)
    }
  }, [port, sendMessage])

  if (isSetup === null) {
    return (
      <div className="bg-[#1a1a2e] h-screen flex items-center justify-center">
        <p className="text-gray-500 text-sm">Starting...</p>
      </div>
    )
  }

  if (!isSetup) {
    return <Setup port={port} onComplete={() => setIsSetup(true)} />
  }

  return (
    <div className="bg-[#1a1a2e] h-screen flex flex-col text-white font-sans">
      {/* Header with tabs */}
      <div className="border-b border-white/10 px-4 py-3 flex items-center gap-4 flex-shrink-0">
        <h1 className="font-bold text-base">Climb</h1>
        <div className="flex gap-1">
          {(['chat', 'history'] as Tab[]).map(t => (
            <button
              key={t}
              onClick={() => handleTabChange(t)}
              className={`px-3 py-1 rounded-md text-xs font-semibold transition-colors capitalize ${
                tab === t ? 'bg-indigo-700 text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
        {tab === 'chat' && chatMatchId && (
          <span className="text-xs text-blue-400 ml-auto">Viewing specific game</span>
        )}
      </div>

      {/* History tab */}
      {tab === 'history' && selectedMatchId === null && (
        <>
          <TrendChart port={port} matches={matches} />
          <HistoryList matches={matches} loading={matchesLoading} error={matchesError} onSelect={setSelectedMatchId} />
        </>
      )}
      {tab === 'history' && selectedMatchId !== null && (
        <GameDetail
          matchId={selectedMatchId}
          port={port}
          onBack={handleBack}
          onAskAboutGame={handleAskAboutGame}
        />
      )}

      {/* Chat tab */}
      {tab === 'chat' && (
        <>
          {focusCard && (
            <FocusCard card={focusCard} onAsk={sendMessage} />
          )}
          {patterns.length > 0 && (
            <div className="px-4 py-2 border-b border-white/10 flex gap-2 overflow-x-auto flex-shrink-0">
              {patterns.map((p) => (
                <button
                  key={p.moment_type}
                  onClick={() => sendMessage(
                    `Tell me about my ${(MOMENT_LABELS[p.moment_type] ?? p.moment_type.replace(/_/g, ' ')).toLowerCase()} pattern`
                  )}
                  className={`flex-shrink-0 text-left px-3 py-2 rounded-lg border-l-4 bg-white/5 hover:bg-white/10 transition-colors ${
                    p.label === 'recurring_issue' ? 'border-red-400' : 'border-green-400'
                  }`}
                >
                  <div className="text-xs font-semibold whitespace-nowrap">
                    {MOMENT_LABELS[p.moment_type] ?? p.moment_type}
                  </div>
                  <div className="text-xs text-gray-400 whitespace-nowrap">
                    {p.games_seen} of {p.total_games} · {Math.round(p.win_rate_with * 100)}% WR
                  </div>
                </button>
              ))}
            </div>
          )}
          <div className="px-4 py-2 border-b border-white/10 flex-shrink-0">
            <button
              onClick={handleSummarize}
              disabled={summarizing || loading}
              className="w-full text-left text-xs text-indigo-300 hover:text-indigo-100 py-1 transition-colors disabled:opacity-50"
            >
              {summarizing ? 'Loading...' : '✦ Summarize today\'s session'}
            </button>
          </div>
          <MessageList messages={messages} />
          {loading && (
            <div className="px-4 pb-1 flex-shrink-0">
              <span className="text-gray-500 text-xs">Analyzing...</span>
            </div>
          )}
          <InputBar onSend={sendMessage} disabled={loading} />
        </>
      )}
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<ChatApp />)
