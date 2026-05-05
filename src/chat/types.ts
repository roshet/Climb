export interface MatchRow {
  match_id: string
  champion: string
  role: string
  result: 'win' | 'loss'
  kda: string
  duration_secs: number
  played_at: string
  moment_count: number
  gold_lost: number
}
