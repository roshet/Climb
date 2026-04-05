import { useState, useEffect, useCallback } from 'react'
import { createRoot } from 'react-dom/client'
import { MessageList } from './MessageList'
import { InputBar } from './InputBar'
import { Setup } from './Setup'
import '../index.css'

declare global {
  interface Window { sidecar: { port: string } }
}

interface Message {
  role: 'user' | 'assistant'
  content: string
}

const SESSION_ID = `session-${Date.now()}`

function ChatApp() {
  const [isSetup, setIsSetup] = useState<boolean | null>(null)
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: "Hi! I'm your personal LoL analyst. Ask me anything about your games — patterns, mistakes, champion performance, or what to focus on to climb." }
  ])
  const [loading, setLoading] = useState(false)
  const [matchId] = useState<string | null>(
    new URLSearchParams(window.location.search).get('matchId')
  )

  const port = window.sidecar?.port ?? '8765'

  useEffect(() => {
    fetch(`http://localhost:${port}/player`)
      .then(r => {
        if (r.status === 404) { setIsSetup(false); return }
        if (r.ok)             { setIsSetup(true);  return }
        setIsSetup(null) // 5xx or unexpected: stay in "Starting..." state
      })
      .catch(() => setIsSetup(null))
  }, [port])

  const sendMessage = useCallback(async (text: string) => {
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setLoading(true)
    try {
      const res = await fetch(`http://localhost:${port}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: SESSION_ID, message: text, match_id: matchId }),
      })
      if (!res.ok) throw new Error('sidecar error')
      const data = await res.json() as { response: string }
      setMessages(prev => [...prev, { role: 'assistant', content: data.response }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error connecting to analyst. Is the sidecar running?' }])
    } finally {
      setLoading(false)
    }
  }, [port, matchId])

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
      <div className="border-b border-white/10 px-4 py-3 flex items-center justify-between">
        <h1 className="font-bold text-base">LoL Analyst</h1>
        {matchId && <span className="text-xs text-blue-400">Viewing specific game</span>}
      </div>
      <MessageList messages={messages} />
      {loading && (
        <div className="px-4 pb-1">
          <span className="text-gray-500 text-xs">Analyzing...</span>
        </div>
      )}
      <InputBar onSend={sendMessage} disabled={loading} />
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<ChatApp />)
