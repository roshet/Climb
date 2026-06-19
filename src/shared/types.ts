// Shared API contract types for the sidecar (FastAPI, localhost:8765).
// Single source of truth — every renderer window imports from here instead of
// redefining its own (previously-diverging) copies.

export interface Message {
  role: 'user' | 'assistant'
  content: string
}

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

export type PatternLabel = 'recurring_issue' | 'win_condition'

/** Full pattern shape returned by `/patterns`. */
export interface Pattern {
  moment_type: string
  label: PatternLabel
  games_seen: number
  total_games: number
  win_rate_with: number
  overall_win_rate: number
  summary: string
}

/** Narrower pattern shape embedded in `/champ-select`'s champ_data. */
export type ChampSelectPattern = Pick<Pattern, 'moment_type' | 'label' | 'summary'>

export interface MatchupEntry {
  opponent: string
  wins: number
  losses: number
  win_rate: number
  dominant_moment: string | null
}

/** `/focus` payload as consumed by the chat window's focus card. */
export interface FocusCardData {
  moment_type: string
  display: string
  coaching_sentence: string
  cta_message: string
  win_rate: number
  games_seen: number
  total_games: number
  streak_clean: number
  history?: boolean[]
  trend?: 'improving' | 'regressing' | null
}

/** A selectable goal metric from `GET /goals/metrics` (the single source of truth). */
export interface GoalMetricInfo {
  key: string
  label: string
  comparison: 'gte' | 'lte'
  is_float: boolean
}

/** A goal with its live-computed streak/history, from `GET /goals` and `POST /goals`. */
export interface Goal {
  id: number
  metric: string
  label: string
  comparison: 'gte' | 'lte'
  target: number
  streak: number
  history: boolean[]
  last_game_met: boolean | null
  games_evaluated: number
}

/** Subset of `/focus` used by the post-game popup. */
export type FocusResult = Pick<
  FocusCardData,
  'moment_type' | 'display' | 'coaching_sentence' | 'cta_message' | 'streak_clean'
>

/** Champion-specific focus embedded in `/champ-select`'s champ_data. */
export interface ChampSelectFocus {
  moment_type: string
  label: string
  games_seen: number
  total_games: number
  avg_gold_lost: number
  champion_specific: boolean
}

export interface ChampData {
  games: number
  wins: number
  win_rate: number
  no_history: boolean
  patterns: ChampSelectPattern[]
  focus: ChampSelectFocus | null
  matchups?: MatchupEntry[]
}

export interface ChampSelectState {
  in_champ_select: boolean
  locked_champion: string | null
  champ_data: ChampData | null
}

export interface Moment {
  timestamp_secs: number
  moment_type: string
  description: string
  counterfactual: string
  gold_impact: number
}

export interface Analysis {
  match_id: string
  champion: string
  role: string
  result: 'win' | 'loss'
  duration_secs: number
  kda: string
  moments: Moment[]
}

export interface ImprovementPattern {
  label: PatternLabel
  moment_type: string
  display: string
  had_in_game: boolean
  streak: number
  recent_rate: number
}

export interface ImprovementData {
  champion: string
  patterns: ImprovementPattern[]
  window: number
}

export interface Alert {
  id: string
  message: string
  alert_type: 'objective' | 'death' | 'pattern'
  expires_at: number
}
