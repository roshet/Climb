import { useState, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import '../index.css'

declare global {
  interface Window { sidecar: { port: string } }
}

interface Alert {
  id: string
  message: string
  alert_type: 'objective' | 'death' | 'pattern'
  expires_at: number
}

const TYPE_BORDER: Record<string, string> = {
  objective: 'border-blue-500 bg-blue-950/80',
  death: 'border-yellow-500 bg-yellow-950/80',
  pattern: 'border-green-500 bg-green-950/80',
}

const TYPE_DOT: Record<string, string> = {
  objective: 'bg-blue-400',
  death: 'bg-yellow-400',
  pattern: 'bg-green-400',
}

function AlertCard({ alert }: { alert: Alert }) {
  const [visible, setVisible] = useState(false)
  const [opacity, setOpacity] = useState(1)

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 10)
    return () => clearTimeout(t)
  }, [])

  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now() / 1000
      const secondsRemaining = alert.expires_at - now
      const newOpacity = Math.min(1, Math.max(0, secondsRemaining / 2))
      setOpacity(newOpacity)
    }, 100)
    return () => clearInterval(interval)
  }, [alert.expires_at])

  const border = TYPE_BORDER[alert.alert_type] ?? 'border-gray-500 bg-gray-900/80'
  const dot = TYPE_DOT[alert.alert_type] ?? 'bg-gray-400'

  return (
    <div
      style={{ opacity }}
      className={`border rounded-lg px-3 py-2 flex items-start gap-2 text-sm text-white shadow-lg transition-all duration-300 ${border} ${
        visible ? 'opacity-100 translate-x-0' : 'opacity-0 translate-x-4'
      }`}
    >
      <div className={`w-2 h-2 rounded-full mt-1 shrink-0 ${dot}`} />
      <span className="leading-snug">{alert.message}</span>
    </div>
  )
}

function OverlayApp() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const port = window.sidecar?.port ?? '8765'

  useEffect(() => {
    const poll = async () => {
      try {
        const res = await fetch(`http://localhost:${port}/live`)
        if (!res.ok) return
        const data = await res.json() as { alerts: Alert[]; in_game: boolean }
        setAlerts(data.alerts ?? [])
      } catch { /* sidecar not ready */ }
    }
    poll()
    const interval = setInterval(poll, 2000)
    return () => clearInterval(interval)
  }, [port])

  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now() / 1000
      setAlerts((prevAlerts) => prevAlerts.filter((alert) => alert.expires_at > now))
    }, 500)
    return () => clearInterval(interval)
  }, [])

  if (alerts.length === 0) return null

  return (
    <div className="fixed top-4 right-4 w-72 flex flex-col gap-2 pointer-events-none select-none">
      {alerts.map((alert) => (
        <AlertCard key={alert.id} alert={alert} />
      ))}
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<OverlayApp />)
