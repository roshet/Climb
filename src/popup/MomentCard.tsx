import { useState } from 'react'
import { POSITIVE_TYPES } from './constants'

interface MomentCardProps {
  timestampSecs: number
  momentType: string
  description: string
  counterfactual: string
  goldImpact: number
}

function formatType(momentType: string): string {
  return momentType.replace(/_/g, ' ').toUpperCase()
}

export function MomentCard({ timestampSecs, momentType, description, counterfactual, goldImpact }: MomentCardProps) {
  const [expanded, setExpanded] = useState(false)
  const mins = Math.floor(timestampSecs / 60)
  const secs = timestampSecs % 60
  const time = `${mins}:${secs.toString().padStart(2, '0')}`
  const isPositive = POSITIVE_TYPES.has(momentType)

  const borderColor = isPositive ? 'border-green-500/30' : 'border-yellow-500/30'
  const bgColor = isPositive ? 'bg-green-500/5' : 'bg-yellow-500/5'
  const labelColor = isPositive ? 'text-green-400' : 'text-yellow-400'
  const dividerColor = isPositive ? 'border-green-500/20' : 'border-yellow-500/20'
  const impactColor = isPositive ? 'text-green-500/50' : 'text-yellow-500/50'

  return (
    <div
      className={`border ${borderColor} ${bgColor} rounded-lg p-3 mb-2 cursor-pointer`}
      onClick={() => setExpanded(prev => !prev)}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`${labelColor} text-[9px] font-semibold tracking-widest uppercase`}>
              {formatType(momentType)}
            </span>
            <span className={`${labelColor} text-[9px] opacity-60`}>{time}</span>
            {goldImpact < 0 && (
              <span className="text-red-400 text-[9px] font-mono ml-auto">
                −{Math.abs(goldImpact).toLocaleString()}g
              </span>
            )}
          </div>
          <p className="text-white text-xs leading-snug">{description}</p>
        </div>
        <span className={`${labelColor} text-xs mt-0.5 shrink-0`}>
          {expanded ? '▲' : '▼'}
        </span>
      </div>

      {expanded && (
        <div className={`border-t ${dividerColor} mt-2 pt-2`}>
          <p className="text-gray-400 text-[11px] leading-relaxed">
            {counterfactual || 'No coaching note available.'}
          </p>
          <p className={`${impactColor} text-[10px] mt-1`}>~{goldImpact}g impact</p>
        </div>
      )}
    </div>
  )
}
