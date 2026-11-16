export type MarketKey = 'totals' | 'player_rebounds' | 'player_threes' | 'player_rebounds_assists' | 'player_blocks' | 'h2h'

export interface Stats {
  bets: number; won: number; lost: number; push: number; units: number
  roi: number | null; hit_rate: number | null; avg_price: number | null; avg_ev: number | null
}
export interface MarketSummary {
  key: MarketKey; label: string; short: string; kind: 'game' | 'prop'; window: string; rule: string; status: string
  two_season: Stats & { ci_low: number }; season_2025_26: Stats; season_2024_25: Stats; live: Stats; spark: number[]
}
export interface Summary {
  markets: MarketSummary[]; winners: number
  totals: {
    two_season: Stats
    season_2025_26: Stats & { months_profit: number; months: number; worst_drop: number; bets_per_day: number }
    live: Stats; live_last_slate: string | null
  }
}
export interface Window { key: string; window: string; at: string; status: string; markets: MarketKey[] }
export interface Team { code: string; city: string; name: string; score: number | null }
export interface Game { game_id: string; tip: string; status: number; status_text: string; home: Team; away: Team; windows: Window[]; picks: number }
export interface Pick {
  market: MarketKey; label: string; short: string; kind: 'game' | 'prop'; window: string; slate: string; game_id: string
  away: string; home: string; who: string; side: string; point: number | null; book: string; price: number; dec: number
  ev: number; p_win: number | null; breakeven: number; p_market: number | null; p_player: number | null; ref: string | null
  decision_utc: string | null; tip_utc: string | null; state: string; result: number | null; profit: number | null
  source: string; confidence: 'A' | 'B' | 'C'
}
export interface Board { day: string; now: string; games: Game[]; noon: Window; picks: Pick[]; days: string[] }
export interface Info {
  app: string; version: string; books: Record<string, string>; require_login: boolean; odds_configured: boolean; auto_picks: boolean
  rule: { name: string; definition: string; disclosure: string[] }
  markets: { key: MarketKey; label: string; short: string; window: string; rule: string; kind: string }[]
}
export interface Job {
  job_id: string; kind: string; status: string; progress: number; eta_seconds: number | null; message: string
  created_at: string; finished_at: string | null
}
export interface LogLine { timestamp: string; level: string; source: string; message: string }
export interface SimResult {
  days: number; sims: number; bankroll: number; bets_per_day: number; pool_days: number; pool_bets: number
  bands: { day: number[]; p5: number[]; p25: number[]; p50: number[]; p75: number[]; p95: number[] }
  sample_paths: number[][]; final: { median: number; mean: number; p5: number; p95: number }
  prob_profit: number; prob_loss_20: number; ruin: number; drawdown_median: number; drawdown_p95: number
  hist: { counts: number[]; edges: number[] }; roi_median: number | null
}
export interface Bet {
  market: MarketKey; season: string; slate: string; book: string; who: string; side: string; point: number | null
  dec: number; ev: number; p_win: number; result: number; profit: number; source: string; price: number
}

const KEY = 'baseline.key'
const ID = 'baseline.id'

export const auth = {
  get key() { try { return localStorage.getItem(KEY) || '' } catch { return '' } },
  get id() { try { return localStorage.getItem(ID) || '' } catch { return '' } },
  set(id: string, key: string) { try { localStorage.setItem(ID, id); localStorage.setItem(KEY, key) } catch { /* private mode */ } },
  clear() { try { localStorage.removeItem(ID); localStorage.removeItem(KEY) } catch { /* noop */ } },
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string> || {}) }
  if (auth.key) headers['X-API-Key'] = auth.key
  if (init.body) headers['Content-Type'] = 'application/json'
  const r = await fetch(path, { ...init, headers })
  if (!r.ok) {
    let msg = r.statusText
    try { msg = (await r.json()).detail || msg } catch { /* not json */ }
    throw new ApiError(r.status, msg)
  }
  return r.json() as Promise<T>
}

export const api = {
  info: () => req<Info>('/api/info'),
  summary: () => req<Summary>('/api/summary'),
  board: (day?: string) => req<Board>(`/api/board${day ? `?day=${day}` : ''}`),
  equity: (markets?: string[]) => req<{ dates: string[]; total: number[]; season: string[]; series: Record<string, number[]> }>(
    `/api/equity${markets?.length ? `?markets=${markets.join(',')}` : ''}`),
  monthly: () => req<{ rows: { month: string; market: MarketKey; units: number; bets: number }[] }>('/api/monthly'),
  books: () => req<(Stats & { book: string })[]>('/api/books'),
  edge: (market?: string) => req<{ buckets: { bucket: string; bets: number; roi: number | null; expected: number | null }[]; calibration: { p: number; actual: number; n: number }[] }>(
    `/api/edge${market ? `?market=${market}` : ''}`),
  bets: (p: Record<string, string | number | undefined>) => {
    const q = new URLSearchParams(Object.entries(p).filter(([, v]) => v !== undefined && v !== '').map(([k, v]) => [k, String(v)]))
    return req<{ total: number; rows: Bet[] }>(`/api/bets?${q}`)
  },
  player: (name: string, market: string, before?: string) => req<{ player: string; stat: string; games: { date: string; matchup: string; value: number; minutes: number }[] }>(
    `/api/player?name=${encodeURIComponent(name)}&market=${market}${before ? `&before=${before}` : ''}`),
  simulate: (body: object) => req<SimResult>('/api/simulate', { method: 'POST', body: JSON.stringify(body) }),
  engine: () => req<{ credits: Record<string, unknown>; plan: { day: string; credits: number; decisions: { key: string; window: string; at: string }[] }; ticks: Record<string, unknown>[]; jobs: Job[]; auto_picks: boolean }>('/api/engine'),
  run: (kind: 'picks' | 'results' | 'test') => req<{ job_id: string }>(`/api/engine/${kind}`, { method: 'POST' }),
  job: (id: string) => req<Job>(`/api/jobs/${id}`),
  logs: (level = 'all', limit = 200) => req<{ logs: LogLine[] }>(`/api/logs?level=${level}&limit=${limit}`),
  login: (identifier: string, api_key: string) => req<{ identifier: string; plan: string; role: string }>('/api/login', { method: 'POST', body: JSON.stringify({ identifier, api_key }) }),
  profile: () => req<{ identifier: string; plan: string; role: string; license_valid: boolean; license_message: string; key_end_date: string; devices: number; max_devices: number }>('/api/profile'),
}

export async function download(path: string) {
  const r = await fetch(path, { headers: auth.key ? { 'X-API-Key': auth.key } : {} })
  if (!r.ok) throw new ApiError(r.status, r.statusText)
  const name = /filename="([^"]+)"/.exec(r.headers.get('Content-Disposition') || '')?.[1] || 'export'
  const url = URL.createObjectURL(await r.blob())
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
  return name
}
