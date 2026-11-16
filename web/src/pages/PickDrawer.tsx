import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'motion/react'
import { X } from 'lucide-react'
import clsx from 'clsx'
import { api, type Pick } from '../lib/api'
import { odds, pct, pctPlain, selection, timeET, units, MARKET_HUE } from '../lib/format'
import { Badge } from '../components/ui'
import { bookName } from './Board'

const STAT_LABEL: Record<string, string> = { REB: 'rebounds', FG3M: 'threes made', BLK: 'blocks', RA: 'rebounds + assists' }

export function PickDrawer({ pick: p, onClose }: { pick: Pick; onClose: () => void }) {
  const { data: sum } = useQuery({ queryKey: ['summary'], queryFn: api.summary })
  const { data: info } = useQuery({ queryKey: ['info'], queryFn: api.info })
  const { data: form } = useQuery({ queryKey: ['player', p.who, p.market, p.slate], queryFn: () => api.player(p.who, p.market, p.slate), enabled: p.kind === 'prop' })
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  const m = sum?.markets.find((x) => x.key === p.market)
  const rule = info?.markets.find((x) => x.key === p.market)?.rule
  const factors = [
    p.p_market != null && { k: 'Market fair price', d: `${p.ref ?? 'reference'} no-vig, before the player model`, v: p.p_market },
    p.p_player != null && { k: 'Player projection model', d: 'recent minutes and per-minute rates, earlier games only', v: p.p_player },
    { k: p.kind === 'prop' ? 'Stacked probability' : 'Fair win probability', d: p.kind === 'prop' ? 'frozen logistic blend of the two' : `${p.ref ?? 'Pinnacle'} no-vig`, v: p.p_win ?? p.breakeven, hi: true },
    { k: 'Break-even at this price', d: `${odds(p.price)} at ${bookName(p.book)}`, v: p.breakeven, be: true },
  ].filter(Boolean) as { k: string; d: string; v: number; hi?: boolean; be?: boolean }[]

  return (
    <>
      <motion.div className="fixed inset-0 z-40 bg-black/60 backdrop-blur-[2px]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
      <motion.aside initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 40, opacity: 0 }} transition={{ duration: .24, ease: [.2, .8, .2, 1] }}
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[520px] flex-col border-l border-line-2 bg-ink-1 shadow-[-40px_0_80px_-20px_rgba(0,0,0,.7)]">
        <div className="relative border-b border-line px-6 pt-5 pb-5">
          <span className="absolute inset-x-0 top-0 h-0.5" style={{ background: MARKET_HUE[p.market] }} />
          <div className="flex items-start justify-between">
            <div className="eyebrow flex items-center gap-2"><i className="h-1.5 w-1.5 rounded-full" style={{ background: MARKET_HUE[p.market] }} />{p.label} · {p.window}</div>
            <button onClick={onClose} className="-mt-1 -mr-2 grid h-8 w-8 place-items-center rounded-sm text-fog-3 hover:bg-ink-3 hover:text-fog-1"><X size={16} /></button>
          </div>
          <div className="display mt-3 text-[40px] text-fog-1">{p.kind === 'prop' ? p.who : `${p.away} @ ${p.home}`}</div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="num rounded-xs bg-volt px-2 py-0.5 text-sm font-semibold text-ink-0">{selection(p)}</span>
            <span className="num text-sm text-fog-1">{odds(p.price)}</span>
            <span className="text-sm text-fog-3">{bookName(p.book)}</span>
            <span className="text-fog-4">·</span>
            <span className="num text-sm text-fog-3">{p.kind === 'prop' && `${p.away} @ ${p.home} · `}tip {timeET(p.tip_utc)} ET</span>
          </div>
        </div>

        <div className="flex-1 space-y-6 overflow-y-auto px-6 py-5">
          <div className="grid grid-cols-3 gap-3">
            <Kpi label="Win probability" value={pctPlain(p.p_win)} tone="text-volt" />
            <Kpi label="Expected value" value={pct(p.ev)} tone="text-volt" />
            <Kpi label="Result" value={p.state === 'graded' ? ((p.result ?? 0) > 0 ? units(p.profit, 2) : (p.result ?? 0) < 0 ? '−1.00u' : 'Push') : p.state.toUpperCase()}
              tone={p.state === 'graded' ? ((p.result ?? 0) > 0 ? 'text-volt' : 'text-loss') : 'text-ember'} />
          </div>

          <section>
            <div className="eyebrow mb-3">Why this pick</div>
            <div className="space-y-3">
              {factors.map((f) => (
                <div key={f.k}>
                  <div className="mb-1 flex items-baseline justify-between gap-3">
                    <div className="min-w-0"><span className={clsx('text-sm', f.hi ? 'text-fog-1' : 'text-fog-2')}>{f.k}</span> <span className="text-xs text-fog-4">{f.d}</span></div>
                    <span className={clsx('num text-sm', f.be ? 'text-ember' : f.hi ? 'text-volt' : 'text-fog-1')}>{pctPlain(f.v)}</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-ink-4">
                    <div className={clsx('h-full rounded-full', f.be ? 'bg-ember/80' : f.hi ? 'bg-volt' : 'bg-fog-3')} style={{ width: `${f.v * 100}%` }} />
                  </div>
                </div>
              ))}
            </div>
            <p className="mt-3 text-xs leading-relaxed text-fog-3">
              The edge is the gap between the {p.kind === 'prop' ? 'stacked' : 'fair'} probability and the break-even of the best price across the eight books:
              <span className="num text-fog-1"> {pctPlain(p.p_win)} vs {pctPlain(p.breakeven)}</span>, an expected return of <span className="num text-volt">{pct(p.ev)}</span> per unit.
            </p>
          </section>

          {p.kind === 'prop' && form && form.games.length > 0 && (
            <section>
              <div className="mb-3 flex items-baseline justify-between">
                <div className="eyebrow">Last {form.games.length} games · {STAT_LABEL[form.stat]}</div>
                <div className="num text-xs text-fog-3">line {p.point} · {p.side}</div>
              </div>
              <FormBars games={form.games} line={p.point ?? 0} side={p.side} />
            </section>
          )}

          {m && (
            <section className="rounded-md border border-line bg-ink-2 p-4">
              <div className="mb-3 flex items-center justify-between">
                <div className="eyebrow">Market track record</div>
                <Badge tone="volt">{m.status}</Badge>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <Kpi label="2 seasons" value={pct(m.two_season.roi)} sub={`${m.two_season.bets.toLocaleString()} bets`} />
                <Kpi label="2025-26" value={pct(m.season_2025_26.roi)} sub={`${m.season_2025_26.bets} bets`} />
                <Kpi label="Live 26-27" value={pct(m.live.roi)} sub={`${m.live.won}-${m.live.lost}`} />
              </div>
              {rule && <p className="mt-3 border-t border-line pt-3 text-xs leading-relaxed text-fog-3"><span className="text-fog-2">Frozen rule.</span> {rule}. Window {p.window}; one pick per player or game at the best price; never refitted.</p>}
            </section>
          )}
        </div>
      </motion.aside>
    </>
  )
}

function Kpi({ label, value, tone, sub }: { label: string; value: string; tone?: string; sub?: string }) {
  return (
    <div className="rounded-sm border border-line bg-ink-2 px-3 py-2.5">
      <div className="eyebrow !text-[9.5px]">{label}</div>
      <div className={clsx('num mt-1 text-lg', tone ?? 'text-fog-1')}>{value}</div>
      {sub && <div className="num text-[11px] text-fog-3">{sub}</div>}
    </div>
  )
}

function FormBars({ games, line, side }: { games: { date: string; matchup: string; value: number; minutes: number }[]; line: number; side: string }) {
  const top = Math.max(line * 1.6, ...games.map((g) => g.value), 1)
  const hits = games.filter((g) => (side === 'over' ? g.value > line : g.value < line)).length
  return (
    <div>
      <div className="relative flex h-32 items-end gap-1.5">
        <div className="absolute inset-x-0 border-t border-dashed border-ember/70" style={{ bottom: `${(line / top) * 100}%` }}>
          <span className="absolute -top-4 right-0 font-mono text-[10px] text-ember">{line}</span>
        </div>
        {games.map((g, i) => {
          const hit = side === 'over' ? g.value > line : g.value < line
          return (
            <div key={i} className="group relative flex flex-1 flex-col items-center justify-end" style={{ height: '100%' }} title={`${g.date} ${g.matchup}: ${g.value} in ${g.minutes} min`}>
              <span className="num mb-1 text-[10px] text-fog-3 opacity-0 transition-opacity group-hover:opacity-100">{g.value}</span>
              <div className={clsx('w-full rounded-t-[2px]', hit ? 'bg-volt' : 'bg-fog-4')} style={{ height: `${Math.max((g.value / top) * 100, 2)}%` }} />
            </div>
          )
        })}
      </div>
      <div className="mt-2 flex justify-between font-mono text-[10.5px] text-fog-3">
        <span>{games[0]?.date.slice(5)}</span>
        <span className="text-fog-2">{hits}/{games.length} would have cashed ({side})</span>
        <span>{games[games.length - 1]?.date.slice(5)}</span>
      </div>
    </div>
  )
}
