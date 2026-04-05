interface TakeawayProps {
  champion: string
  result: 'win' | 'loss'
  durationSecs: number
  kda: string
}

export function Takeaway({ champion, result, durationSecs, kda }: TakeawayProps) {
  const mins = Math.floor(durationSecs / 60)
  const resultColor = result === 'win' ? 'text-blue-400' : 'text-red-400'

  return (
    <div className="border-t border-white/10 pt-3 mt-3">
      <div className="flex justify-between items-center mb-2">
        <span className="text-gray-300 text-sm font-medium">{champion}</span>
        <span className={`text-sm font-bold uppercase ${resultColor}`}>{result}</span>
      </div>
      <div className="flex gap-3 text-xs text-gray-500">
        <span>KDA {kda}</span>
        <span>{mins}m</span>
      </div>
    </div>
  )
}
