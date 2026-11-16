export const pct = (x: number | null | undefined, d = 1, sign = true) =>
  x == null || !isFinite(x) ? '—' : `${sign && x > 0 ? '+' : ''}${(x * 100).toFixed(d)}%`

export const pctPlain = (x: number | null | undefined, d = 1) => (x == null ? '—' : `${(x * 100).toFixed(d)}%`)

export const units = (x: number | null | undefined, d = 1) =>
  x == null ? '—' : `${x > 0 ? '+' : x < 0 ? '−' : ''}${Math.abs(x).toFixed(d)}u`

export const odds = (p: number | null | undefined) => (p == null ? '—' : p > 0 ? `+${p}` : `${p}`.replace('-', '−'))

export const int = (x: number | null | undefined) => (x == null ? '—' : x.toLocaleString('en-US'))

export const money = (x: number) => `${x < 0 ? '−' : ''}$${Math.abs(x).toLocaleString('en-US', { maximumFractionDigits: 0 })}`

export const tone = (x: number | null | undefined) => (x == null ? 'text-fog-2' : x > 0 ? 'text-volt' : x < 0 ? 'text-loss' : 'text-fog-2')

const ET = 'America/New_York'

export const timeET = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleTimeString('en-US', { timeZone: ET, hour: 'numeric', minute: '2-digit' }) : '—'

export const timeLocal = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '—'

export const dayLabel = (day: string, style: 'short' | 'long' = 'short') => {
  const d = new Date(`${day}T12:00:00`)
  return style === 'short'
    ? d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
    : d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })
}

export const countdown = (ms: number) => {
  if (ms <= 0) return '00:00:00'
  const s = Math.floor(ms / 1000)
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60
  return [h, m, r].map((v) => String(v).padStart(2, '0')).join(':')
}

export const selection = (p: { kind: string; side: string; point: number | null; who: string; home: string; away: string }) => {
  const side = p.side.toUpperCase()
  if (p.kind === 'prop') return `${side} ${p.point ?? ''}`.trim()
  if (p.side === 'home') return `${p.home} ML`
  if (p.side === 'away') return `${p.away} ML`
  return `${side} ${p.point ?? ''}`.trim()
}

export const MARKET_HUE: Record<string, string> = {
  totals: '#7cc7ff',
  player_rebounds: '#c8f560',
  player_threes: '#ff6a2b',
  player_rebounds_assists: '#b79cff',
  player_blocks: '#f2c94c',
  h2h: '#5eead4',
}
