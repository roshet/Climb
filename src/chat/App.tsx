import { useState, useEffect, useCallback } from 'react'
import { createRoot } from 'react-dom/client'
import { initRendererLogForwarding } from '../shared/log'
import { OfflineBanner } from './OfflineBanner'
import { MessageList } from './MessageList'
import { InputBar } from './InputBar'
import { Setup } from './Setup'
import { HistoryList } from './HistoryList'
import { GameDetail } from './GameDetail'
import { TrendChart } from './TrendChart'
import { FocusCard, FocusCardData } from './FocusCard'
import { GoalsPanel } from './GoalsPanel'
import { MatchRow } from './types'
import { Message, Pattern, MatchupEntry } from '../shared/types'
import { getJson, postJson } from '../shared/api'
import '../index.css'

type Tab = 'chat' | 'history' | 'goals'

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
  teamfight_won: 'Team Fights Won',
  teamfight_lost: 'Team Fights Lost',
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
  const [backfilling, setBackfilling] = useState(false)
  const [matchups, setMatchups] = useState<MatchupEntry[]>([])
  const [analystOffline, setAnalystOffline] = useState(false)

  const port = window.sidecar?.port ?? '8765'

  useEffect(() => {
    let cancelled = false
    const check = () => {
      fetch(`http://localhost:${port}/player`)
        .then(r => {
          if (cancelled) return
          if (r.status === 404) { setIsSetup(false); return }
          if (r.ok)             { setIsSetup(true);  return }
          setTimeout(check, 1000)
        })
        .catch(() => { if (!cancelled) setTimeout(check, 1000) })
    }
    check()
    return () => { cancelled = true }
  }, [port])

  useEffect(() => {
    if (isSetup !== true) return
    if (tab !== 'chat') return
    getJson<FocusCardData>('/focus').then(setFocusCard)
  }, [isSetup, tab])

  useEffect(() => {
    if (isSetup !== true) return
    getJson<{ patterns: Pattern[] }>('/patterns').then(data => setPatterns(data?.patterns ?? []))
  }, [isSetup])

  useEffect(() => {
    if (isSetup !== true) return
    getJson<{ matchups: MatchupEntry[] }>('/matchups').then(data => setMatchups(data?.matchups ?? []))
  }, [isSetup])

  useEffect(() => {
    if (isSetup !== true) return
    let fails = 0
    const check = () => {
      fetch(`http://localhost:${port}/status`)
        .then(r => r.ok ? r.json() : null)
        .then((data: { backfill_running?: boolean } | null) => {
          fails = 0
          setAnalystOffline(false)
          const running = data?.backfill_running ?? false
          setBackfilling(running)
          if (!running) {
            fetch(`http://localhost:${port}/patterns`)
              .then(r => r.ok ? r.json() : { patterns: [] })
              .then((d: { patterns: Pattern[] }) => setPatterns(d.patterns))
              .catch(() => {})
            fetch(`http://localhost:${port}/focus`)
              .then(r => r.ok ? r.json() : null)
              .then(d => setFocusCard(d as FocusCardData | null))
              .catch(() => {})
            fetch(`http://localhost:${port}/matchups`)
              .then(r => r.ok ? r.json() : { matchups: [] })
              .then((d: { matchups: MatchupEntry[] }) => setMatchups(d.matchups))
              .catch(() => {})
          }
        })
        .catch(() => {
          fails += 1
          if (fails >= 2) setAnalystOffline(true)
        })
    }
    check()
    const id = setInterval(check, 4000)
    return () => clearInterval(id)
  }, [port, isSetup])

  useEffect(() => {
    if (tab !== 'history' || !isSetup) return
    setMatchesLoading(true)
    setMatchesError(false)
    getJson<MatchRow[]>('/matches?last_n=20').then(data => {
      if (Array.isArray(data)) setMatches(data.slice().reverse())
      else setMatchesError(true)
      setMatchesLoading(false)
    })
  }, [tab, isSetup])

  const sendMessage = useCallback(async (text: string) => {
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setLoading(true)
    const data = await postJson<{ response: string }>('/chat', {
      session_id: SESSION_ID, message: text, match_id: chatMatchId,
    })
    setMessages(prev => [...prev, {
      role: 'assistant',
      content: data?.response ?? 'Error connecting to analyst. Is the sidecar running?',
    }])
    setLoading(false)
  }, [chatMatchId])

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
    const data = await getJson<MatchRow[]>('/matches?last_n=20')
    if (Array.isArray(data)) {
      const all = data.slice().reverse()
      const today = new Date()
      today.setHours(0, 0, 0, 0)
      const todayGames = all.filter(m => new Date(m.played_at) >= today)
      const games = todayGames.length > 0 ? todayGames : all.slice(-5)
      sendMessage(buildSessionMessage(games, todayGames.length > 0))
    }
    setSummarizing(false)
  }, [sendMessage])

  if (isSetup === null) {
    return (
      <div className="bg-[#1a1a2e] h-screen flex items-center justify-center">
        <p className="text-gray-500 text-sm">Starting...</p>
      </div>
    )
  }

  if (!isSetup) {
    return <Setup onComplete={() => setIsSetup(true)} />
  }

  return (
    <div className="bg-[#1a1a2e] h-screen flex flex-col text-white font-sans">
      {/* Header with tabs */}
      <div className="border-b border-white/10 px-4 py-3 flex items-center gap-4 flex-shrink-0">
        <h1 className="font-bold text-base">Climb</h1>
        <div className="flex gap-1">
          {(['chat', 'history', 'goals'] as Tab[]).map(t => (
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

      <OfflineBanner offline={analystOffline} />

      {/* History tab */}
      {tab === 'history' && selectedMatchId === null && (
        <>
          <TrendChart matches={matches} />
          <HistoryList matches={matches} loading={matchesLoading} error={matchesError} onSelect={setSelectedMatchId} />
        </>
      )}
      {tab === 'history' && selectedMatchId !== null && (
        <GameDetail
          matchId={selectedMatchId}
          onBack={handleBack}
          onAskAboutGame={handleAskAboutGame}
        />
      )}

      {/* Chat tab */}
      {tab === 'chat' && (
        <>
          {backfilling && (
            <div className="mx-3 mt-2 px-3 py-2 bg-indigo-950/60 border border-indigo-500/40 rounded-lg flex items-center gap-2 flex-shrink-0">
              <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse shrink-0" />
              <p className="text-indigo-300 text-[11px]">Analyzing your match history — focus card ready in ~1 min</p>
            </div>
          )}
          {focusCard && (
            <FocusCard card={focusCard} onAsk={sendMessage} />
          )}
          {!backfilling && patterns.length === 0 && !focusCard && (
            <div className="mx-3 mt-2 px-3 py-2 bg-white/5 border border-white/10 rounded-lg flex-shrink-0">
              <p className="text-gray-400 text-[11px] leading-relaxed">
                Play a few games and your focus card will appear here — your top recurring issue with coaching tips.
              </p>
            </div>
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
          {matchups.length > 0 && (
            <div className="px-4 py-2 border-b border-white/10 flex-shrink-0">
              <div className="text-[8px] uppercase tracking-widest text-gray-500 mb-2">tough matchups</div>
              {matchups.map((m) => (
                <div key={m.opponent} className="flex justify-between items-center mb-1.5">
                  <div>
                    <span className="text-[10px] text-gray-200">vs {m.opponent}</span>
                    {m.dominant_moment && (
                      <span className="text-[8px] text-gray-500 ml-1">
                        {m.dominant_moment.replace(/_/g, ' ')}
                      </span>
                    )}
                  </div>
                  <span className={`text-[10px] font-bold ${
                    m.win_rate < 0.4 ? 'text-red-400' : 'text-yellow-400'
                  }`}>
                    {m.wins}W {m.losses}L · {Math.round(m.win_rate * 100)}%
                  </span>
                </div>
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

      {/* Goals tab */}
      {tab === 'goals' && <GoalsPanel />}
    </div>
  )
}

initRendererLogForwarding()
createRoot(document.getElementById('root')!).render(<ChatApp />)
