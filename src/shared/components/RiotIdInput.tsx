interface RiotIdInputProps {
  gameName: string
  tagLine: string
  onGameNameChange: (value: string) => void
  onTagLineChange: (value: string) => void
}

export function RiotIdInput({ gameName, tagLine, onGameNameChange, onTagLineChange }: RiotIdInputProps) {
  return (
    <div className="flex gap-2">
      <input
        className="flex-1 bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none placeholder-gray-500"
        placeholder="Game Name"
        value={gameName}
        onChange={e => onGameNameChange(e.target.value)}
      />
      <span className="text-gray-500 self-center">#</span>
      <input
        className="w-20 bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none placeholder-gray-500"
        placeholder="TAG"
        value={tagLine}
        onChange={e => onTagLineChange(e.target.value)}
      />
    </div>
  )
}
