interface MomentCardProps {
  timestampSecs: number
  momentType: string
  description: string
  counterfactual: string
  goldImpact: number
}

export function MomentCard({ timestampSecs, description, counterfactual, goldImpact }: MomentCardProps) {
  const mins = Math.floor(timestampSecs / 60)
  const secs = timestampSecs % 60
  const time = `${mins}:${secs.toString().padStart(2, '0')}`

  return (
    <div className="border border-yellow-500/30 bg-yellow-500/5 rounded-lg p-3 mb-2">
      <div className="flex items-start gap-2">
        <span className="text-yellow-400 text-sm font-mono mt-0.5">⚠ {time}</span>
        <div>
          <p className="text-white text-sm">{description}</p>
          <p className="text-gray-400 text-xs mt-1">{counterfactual}</p>
          <p className="text-yellow-500/70 text-xs mt-1">~{goldImpact}g impact</p>
        </div>
      </div>
    </div>
  )
}
