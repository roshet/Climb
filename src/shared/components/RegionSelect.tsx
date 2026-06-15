// Values must match REGIONAL_ROUTING keys in sidecar/riot_client.py — any value not
// in that map silently falls through to the "americas" routing cluster.
const REGIONS = ['NA1', 'EUW1', 'EUNE1', 'KR', 'BR1', 'LAN', 'LAS', 'OC1', 'TR1', 'RU', 'JP1']

interface RegionSelectProps {
  value: string
  onChange: (region: string) => void
}

export function RegionSelect({ value, onChange }: RegionSelectProps) {
  return (
    <select
      className="w-full bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none [color-scheme:dark]"
      value={value}
      onChange={e => onChange(e.target.value)}
    >
      {REGIONS.map(r => (
        <option key={r} value={r} className="bg-[#1a1a2e] text-white">{r}</option>
      ))}
    </select>
  )
}
