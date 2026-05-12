export interface FocusCardData {
  moment_type: string
  display: string
  coaching_sentence: string
  cta_message: string
  win_rate: number
  games_seen: number
  total_games: number
  streak_clean: number
}

interface FocusCardProps {
  card: FocusCardData
  onAsk: (message: string) => void
}

export function FocusCard({ card, onAsk }: FocusCardProps) {
  return (
    <div className="mx-4 mb-2 bg-[#1a1a3a] border border-indigo-500/40 rounded-lg px-3 py-2 flex-shrink-0">
      <div className="text-[9px] font-bold tracking-wider text-indigo-400 mb-1">
        🎯 FOCUS FOR NEXT GAME
      </div>
      <div className="text-sm font-semibold text-white mb-1">{card.display}</div>
      <div className="text-xs text-gray-400 leading-relaxed mb-2">{card.coaching_sentence}</div>
      {card.streak_clean >= 1 && (
        <div className="bg-green-950/50 border border-green-500/30 rounded px-2 py-1 mb-2">
          <span className="text-green-400 text-[10px]">
            ↑ Clean last {card.streak_clean} game{card.streak_clean === 1 ? '' : 's'} — keep it up
          </span>
        </div>
      )}
      <div className="flex items-center">
        <span className="text-[10px] text-red-400">{Math.round(card.win_rate * 100)}% WR</span>
        <span className="text-gray-600 mx-1.5">·</span>
        <span className="text-[10px] text-gray-500">
          {card.games_seen} of {card.total_games} games
        </span>
        <button
          onClick={() => { if (card.cta_message) onAsk(card.cta_message) }}
          className="ml-auto text-[10px] bg-indigo-600 hover:bg-indigo-500 text-white px-2 py-1 rounded transition-colors"
        >
          Ask Claude →
        </button>
      </div>
    </div>
  )
}
