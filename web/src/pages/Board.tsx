import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams, useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'motion/react'
import clsx from 'clsx'
import { ChevronLeft, ChevronRight, FileDown, FileSpreadsheet, Clock3, Radio } from 'lucide-react'
import { api, download, type Board as BoardT, type Pick, type Game } from '../lib/api'
import { countdown, dayLabel, odds, pct, pctPlain, selection, timeET, units, MARKET_HUE, tone } from '../lib/format'
import { Badge, Button, Dot, Empty, PageHead, Panel, ProbBar, Seg, Skeleton, Stat } from '../components/ui'
import { useJobs } from '../components/jobs'
import { PickDrawer } from './PickDrawer'

function useNow(ms = 1000) {
  const [n, setN] = useState(Date.now())
  useEffect(() => { const t = setInterval(() => setN(Date.now()), ms); return () => clearInterval(t) }, [ms])
  return n
}

const WINDOW_LABEL: Record<string, string> = { NOON: 'Moneyline', T60P: 'Threes · Blocks', T30P: 'Rebounds · Reb+Ast', T30G: 'Game totals' }

export function Board() {
  const { day } = useParams()
  const nav = useNavigate()
  const { data, isLoading } = useQuery({ queryKey: ['board', day], queryFn: () => api.board(day), refetchInterval: 60000 })
  const [filter, setFilter] = useState<string>('all')
  const [open, setOpen] = useState<Pick | null>(null)
  const { toast } = useJobs()

  const picks = useMemo(() => (data?.picks ?? []).filter((p) => filter === 'all' || p.market === filter), [data, filter])
  const go = (d: string) => nav(`/day/${d}`)

  if (isLoading || !data) return <BoardSkeleton />
  const i = data.days.indexOf(data.day)
  const graded = data.picks.filter((p) => p.state === 'graded')
  const won = graded.filter((p) => (p.result ?? 0) > 0).length
  const lost = graded.filter((p) => (p.result ?? 0) < 0).length
  const u = graded.reduce((a, p) => a + (p.profit ?? 0), 0)

  const exp = async (fmt: 'csv' | 'pdf') => {
    try { const n = await download(`/api/export/picks.${fmt}?day=${data.day}`); toast({ title: 'Export ready', body: n, tone: 'ok' }) }
    catch (e) { toast({ title: 'Export failed', body: String(e), tone: 'err' }) }
  }

  return (
    <>
      <PageHead kicker={`Slate · ${dayLabel(data.day, 'long')}`} title={<>The <span className="text-volt">Board</span></>}>
        <div className="flex max-w-full items-center gap-1 overflow-x-auto rounded-sm border border-line bg-ink-1 p-0.5">
          <button disabled={i <= 0} onClick={() => go(data.days[i - 1])} className="grid h-7 w-7 place-items-center rounded-xs text-fog-2 hover:bg-ink-3 disabled:opacity-30"><ChevronLeft size={15} /></button>
          {data.days.slice(Math.max(0, i - 2), i + 3).map((d) => (
            <button key={d} onClick={() => go(d)} className={clsx('h-7 shrink-0 rounded-xs px-2.5 font-mono text-[11px] whitespace-nowrap uppercase', Math.abs(data.days.indexOf(d) - i) > 1 && 'hidden sm:block', d === data.day ? 'bg-volt text-ink-0' : 'text-fog-3 hover:bg-ink-3 hover:text-fog-1')}>
              {dayLabel(d).replace(',', '')}
            </button>
          ))}
          <button disabled={i >= data.days.length - 1} onClick={() => go(data.days[i + 1])} className="grid h-7 w-7 place-items-center rounded-xs text-fog-2 hover:bg-ink-3 disabled:opacity-30"><ChevronRight size={15} /></button>
        </div>
        <Button variant="outline" size="sm" onClick={() => exp('csv')}><FileSpreadsheet size={14} />CSV</Button>
        <Button variant="outline" size="sm" onClick={() => exp('pdf')}><FileDown size={14} />PDF</Button>
      </PageHead>

      <div className="grid grid-cols-12 gap-4">
        <NextWindow data={data} />
        <div className="panel col-span-12 grid grid-cols-2 gap-x-6 gap-y-5 p-5 lg:col-span-4">
          <Stat label="Games" value={data.games.length} sub={`${data.games.filter((g) => g.status === 3).length} final`} />
          <Stat label="Picks" value={data.picks.length} sub={`${new Set(data.picks.map((p) => p.market)).size} of 6 markets`} />
          <Stat label="Record" value={<>{won}<span className="text-fog-4">-</span>{lost}</>} sub={graded.length ? `${data.picks.length - graded.length} pending` : 'no results yet'} />
          <Stat label="Units" value={graded.length ? units(u) : '—'} tone={tone(graded.length ? u : null)} sub="flat 1u per pick" />
        </div>
      </div>

      <Timeline data={data} />

      <div className="mt-6 mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h2 className="display text-[28px]">Picks</h2>
          <span className="num text-xs text-fog-3">{picks.length} shown</span>
        </div>
        <Seg value={filter} onChange={setFilter} className="max-w-full overflow-x-auto"
          options={[{ value: 'all', label: 'All' }, ...['totals', 'player_rebounds', 'player_threes', 'player_rebounds_assists', 'player_blocks', 'h2h'].map((k) => ({
            value: k, label: <span className="flex items-center gap-1.5"><i className="h-1.5 w-1.5 rounded-full" style={{ background: MARKET_HUE[k] }} />{({ totals: 'TOT', player_rebounds: 'REB', player_threes: '3PM', player_rebounds_assists: 'R+A', player_blocks: 'BLK', h2h: 'ML' } as Record<string, string>)[k]}</span>,
          }))]} />
      </div>

      {picks.length ? (
        <div className="panel overflow-hidden">
          <div className="hidden grid-cols-[minmax(0,2.3fr)_minmax(0,1.1fr)_minmax(0,1fr)_minmax(0,1.6fr)_70px_90px] gap-4 border-b border-line px-4 py-2 lg:grid">
            {['Selection', 'Market', 'Best price', 'Win prob vs break-even', 'Edge', 'Status'].map((h) => <div key={h} className="eyebrow">{h}</div>)}
          </div>
          <motion.div initial="h" animate="s" variants={{ s: { transition: { staggerChildren: .025 } } }}>
            {picks.map((p, k) => <PickRow key={k} p={p} onOpen={() => setOpen(p)} />)}
          </motion.div>
        </div>
      ) : (
        <div className="panel"><Empty icon={<Radio size={28} />} title={data.picks.length ? 'No picks in this market today' : 'No picks logged for this day yet'}>
          Picks are made inside each market's decision window (moneyline at 12:00 ET, threes and blocks 60 minutes before tip, rebounds, reb+ast and totals 30 minutes before tip) and only when the edge clears the frozen floor. Some nights a market has none.
        </Empty></div>
      )}

      <div className="mt-8 mb-3 flex items-baseline gap-3">
        <h2 className="display text-[28px]">Games</h2>
        <span className="num text-xs text-fog-3">tip times ET</span>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {data.games.map((g) => <GameTile key={g.game_id} g={g} picks={data.picks.filter((p) => p.game_id.replace(/^0+/, '') === g.game_id.replace(/^0+/, ''))} onPick={setOpen} />)}
      </div>

      <AnimatePresence>{open && <PickDrawer pick={open} onClose={() => setOpen(null)} />}</AnimatePresence>
    </>
  )
}

function NextWindow({ data }: { data: BoardT }) {
  const now = useNow()
  const all = [{ ...data.noon, window: 'NOON' }, ...data.games.flatMap((g) => g.windows.map((w) => ({ ...w, game: g })))]
  const seen = new Set<string>()
  const upcoming = all.filter((w) => new Date(w.at).getTime() > now).sort((a, b) => +new Date(a.at) - +new Date(b.at))
    .filter((w) => { const k = `${w.window}|${w.at}`; if (seen.has(k)) return false; seen.add(k); return true })
  const next = upcoming[0]
  const ms = next ? new Date(next.at).getTime() - now : 0
  const sameTime = next ? upcoming.filter((w) => w.at === next.at) : []
  return (
    <div className="panel relative col-span-12 overflow-hidden p-5 lg:col-span-8">
      <CourtArc />
      <div className="relative flex flex-wrap items-end justify-between gap-6">
        <div>
          <div className="eyebrow mb-3 flex items-center gap-2"><Clock3 size={12} /> {next ? 'Next decision window' : 'All windows closed'}</div>
          <div className="display num text-[64px] leading-none tracking-tight text-fog-1 sm:text-[92px]" style={{ fontFamily: 'var(--font-display)' }}>
            {next ? countdown(ms) : 'FINAL'}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-fog-2">
            {next ? (
              <>
                <Badge tone="ember"><Dot tone="ember" pulse />{next.window === 'NOON' ? '12:00 ET' : (next.window ?? '').replace('P', '').replace('G', '').replace('T', 'T-')}</Badge>
                <span>{WINDOW_LABEL[next.window]}</span>
                <span className="text-fog-4">·</span>
                <span className="num text-fog-3">{timeET(next.at)} ET</span>
                {sameTime.length > 1 && <span className="num text-fog-3">· {sameTime.length} windows</span>}
              </>
            ) : <span className="text-fog-3">Every pick for this slate has been made. Results grade automatically after the games.</span>}
          </div>
        </div>
        <div className="grid w-full grid-cols-3 gap-2 text-right sm:w-auto">
          {[['NOON', '12:00 ET', 'ML'], ['T60', 'T-60', '3PM · BLK'], ['T30', 'T-30', 'REB · R+A · TOT']].map(([k, w, m]) => (
            <div key={k} className="rounded-sm border border-line bg-ink-1/60 px-3 py-2">
              <div className="num text-sm text-fog-1">{w}</div>
              <div className="eyebrow mt-0.5 !text-[9.5px]">{m}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function CourtArc() {
  return (
    <svg className="pointer-events-none absolute -top-10 -right-16 h-[260px] w-[420px] opacity-[.09]" viewBox="0 0 420 260" fill="none">
      <circle cx="300" cy="40" r="180" stroke="#c8f560" strokeWidth="1.5" />
      <circle cx="300" cy="40" r="60" stroke="#c8f560" strokeWidth="1.5" />
      <rect x="240" y="-40" width="120" height="190" stroke="#c8f560" strokeWidth="1.5" />
      <path d="M0 150h420" stroke="#c8f560" strokeWidth="1.5" />
    </svg>
  )
}

function Timeline({ data }: { data: BoardT }) {
  const now = useNow(15000)
  if (!data.games.length) return null
  const start = new Date(data.noon.at).getTime() - 30 * 60000
  const end = Math.max(...data.games.map((g) => new Date(g.tip).getTime())) + 30 * 60000
  const x = (t: number) => `${Math.max(0, Math.min(1, (t - start) / (end - start))) * 100}%`
  const tips = [...new Set(data.games.map((g) => g.tip))]
  const hours: number[] = []
  for (let t = Math.ceil(start / 3600000) * 3600000; t <= end; t += 3600000) hours.push(t)
  return (
    <div className="panel mt-4 px-5 pt-4 pb-5">
      <div className="mb-5 flex items-center justify-between">
        <div className="eyebrow">Decision timeline</div>
        <div className="flex items-center gap-4 font-mono text-[10.5px] text-fog-3">
          <span className="flex items-center gap-1.5"><i className="h-2 w-2 rotate-45 bg-volt" />Window</span>
          <span className="flex items-center gap-1.5"><i className="h-2.5 w-0.5 bg-fog-2" />Tip-off</span>
          <span className="flex items-center gap-1.5"><i className="h-2.5 w-0.5 bg-ember" />Now</span>
        </div>
      </div>
      <div className="relative h-16">
        <div className="absolute top-7 right-0 left-0 h-px bg-line-2" />
        {hours.map((h) => (
          <div key={h} className="absolute top-9 -translate-x-1/2 font-mono text-[10px] text-fog-4" style={{ left: x(h) }}>
            {new Date(h).toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour: 'numeric' })}
          </div>
        ))}
        <Marker at={data.noon.at} label="ML" left={x(new Date(data.noon.at).getTime())} done={data.noon.status !== 'upcoming'} />
        {tips.map((t) => {
          const tt = new Date(t).getTime()
          const n = data.games.filter((g) => g.tip === t).length
          return (
            <div key={t}>
              <Marker at={new Date(tt - 3600000).toISOString()} label="60" left={x(tt - 3600000)} done={now > tt - 3600000} />
              <Marker at={new Date(tt - 1800000).toISOString()} label="30" left={x(tt - 1800000)} done={now > tt - 1800000} />
              <div className="absolute top-4.5 h-5 w-0.5 -translate-x-1/2 rounded-full bg-fog-2" style={{ left: x(tt) }} title={`${n} tip(s) ${timeET(t)} ET`} />
              <div className="absolute -top-0.5 -translate-x-1/2 font-mono text-[10px] whitespace-nowrap text-fog-2" style={{ left: x(tt) }}>{n}×</div>
            </div>
          )
        })}
        {now > start && now < end && <div className="absolute top-2 h-10 w-0.5 -translate-x-1/2 rounded-full bg-ember shadow-[0_0_12px_#ff6a2b]" style={{ left: x(now) }} />}
      </div>
    </div>
  )
}

function Marker({ left, label, done, at }: { left: string; label: string; done: boolean; at: string }) {
  return (
    <div className="group absolute top-5.5 -translate-x-1/2" style={{ left }} title={`${label} · ${timeET(at)} ET`}>
      <div className={clsx('h-2.5 w-2.5 rotate-45 border', done ? 'border-volt-dim bg-volt-dim/40' : 'border-volt bg-volt shadow-[0_0_10px_rgba(200,245,96,.6)]')} />
    </div>
  )
}

function PickRow({ p, onOpen }: { p: Pick; onOpen: () => void }) {
  const st = p.state === 'graded' ? ((p.result ?? 0) > 0 ? 'won' : (p.result ?? 0) < 0 ? 'lost' : 'push') : p.state
  return (
    <motion.button variants={{ h: { opacity: 0, y: 4 }, s: { opacity: 1, y: 0 } }} onClick={onOpen}
      className="group relative grid w-full grid-cols-[1fr_auto] items-center gap-x-4 gap-y-2 border-b border-line px-4 py-3 text-left transition-colors last:border-b-0 hover:bg-ink-3/60 lg:grid-cols-[minmax(0,2.3fr)_minmax(0,1.1fr)_minmax(0,1fr)_minmax(0,1.6fr)_70px_90px]">
      <span className="absolute inset-y-2 left-0 w-0.5 rounded-full" style={{ background: MARKET_HUE[p.market] }} />
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="truncate text-[15px] font-medium text-fog-1">{p.kind === 'prop' ? p.who : `${p.away} @ ${p.home}`}</span>
          <Badge tone={p.confidence === 'A' ? 'volt' : p.confidence === 'B' ? 'ice' : 'muted'}>{p.confidence}</Badge>
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-xs text-fog-3">
          <span className="num text-fog-1">{selection(p)}</span>
          <span className="text-fog-4">·</span>
          <span className="num">{p.kind === 'prop' ? `${p.away} @ ${p.home}` : ''} {timeET(p.tip_utc)}</span>
        </div>
      </div>
      <div className="hidden min-w-0 lg:block">
        <div className="truncate text-sm text-fog-2">{p.label}</div>
        <div className="eyebrow mt-0.5">{p.window}</div>
      </div>
      <div className="text-right lg:text-left">
        <div className="num text-[15px] text-fog-1">{odds(p.price)}</div>
        <div className="truncate text-xs text-fog-3">{bookName(p.book)}</div>
      </div>
      <div className="col-span-2 min-w-0 lg:col-span-1">
        <div className="mb-1.5 flex justify-between font-mono text-[11px]">
          <span className="text-volt">{pctPlain(p.p_win)}</span>
          <span className="text-fog-3">BE {pctPlain(p.breakeven)}</span>
        </div>
        <ProbBar p={p.p_win} be={p.breakeven} />
      </div>
      <div className="num hidden text-sm text-volt lg:block">{pct(p.ev)}</div>
      <div className="hidden lg:block">
        {st === 'won' ? <Badge tone="volt">Won {units(p.profit, 2)}</Badge> : st === 'lost' ? <Badge tone="loss">Lost</Badge> : st === 'push' ? <Badge>Push</Badge>
          : st === 'void' ? <Badge>Void</Badge> : <Badge tone="ember"><Dot tone="ember" pulse />Pending</Badge>}
      </div>
    </motion.button>
  )
}

export const bookName = (b: string) => ({ betmgm: 'BetMGM', betrivers: 'BetRivers', draftkings: 'DraftKings', espnbet: 'ESPN BET', fanatics: 'Fanatics', fanduel: 'FanDuel', hardrockbet: 'Hard Rock', williamhill_us: 'Caesars' } as Record<string, string>)[b] ?? b

function GameTile({ g, picks, onPick }: { g: Game; picks: Pick[]; onPick: (p: Pick) => void }) {
  const final = g.status === 3, live = g.status === 2
  const win = final && g.home.score != null && g.away.score != null ? (g.home.score > g.away.score ? 'home' : 'away') : null
  return (
    <div className="panel group overflow-hidden transition-colors hover:border-line-2">
      <div className="flex items-center justify-between border-b border-line px-4 py-2">
        <span className="num text-xs text-fog-2">{timeET(g.tip)} ET</span>
        {live ? <Badge tone="ember"><Dot tone="ember" pulse />Live</Badge> : final ? <Badge>Final</Badge> : <Badge tone="ice">Scheduled</Badge>}
      </div>
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 px-4 py-4">
        {(['away', 'home'] as const).map((s, k) => (
          <div key={s} className={clsx('min-w-0', k === 1 && 'order-3 text-right')}>
            <div className={clsx('display text-[38px]', win && win !== s ? 'text-fog-3' : 'text-fog-1')}>{g[s].code}</div>
            <div className="truncate text-xs text-fog-3">{g[s].name}</div>
          </div>
        ))}
        <div className="order-2 text-center">
          {g.home.score != null && (final || live)
            ? <div className="num text-lg text-fog-1">{g.away.score}<span className="px-1 text-fog-4">:</span>{g.home.score}</div>
            : <div className="font-mono text-xs text-fog-4">@</div>}
        </div>
      </div>
      <div className="flex items-center gap-1.5 border-t border-line px-4 py-2.5">
        {g.windows.map((w) => (
          <span key={w.key} title={`${w.window} · ${timeET(w.at)} ET · ${w.status}`}
            className={clsx('h-1 flex-1 rounded-full', w.status === 'ok' ? 'bg-volt' : w.status === 'open' ? 'bg-ember pulse-dot' : w.status === 'missed' ? 'bg-loss/70' : w.status === 'upcoming' ? 'bg-ink-4' : 'bg-fog-4/50')} />
        ))}
        <span className="ml-2 font-mono text-[10.5px] text-fog-3">{picks.length} pick{picks.length === 1 ? '' : 's'}</span>
      </div>
      {picks.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-4 pb-3">
          {picks.slice(0, 4).map((p, i) => (
            <button key={i} onClick={() => onPick(p)} className="flex items-center gap-1.5 rounded-xs border border-line bg-ink-1 px-1.5 py-0.5 font-mono text-[10.5px] text-fog-2 hover:border-line-2 hover:text-fog-1">
              <i className="h-1.5 w-1.5 rounded-full" style={{ background: MARKET_HUE[p.market] }} />
              {p.kind === 'prop' ? p.who.split(' ').slice(-1)[0] : p.short} {selection(p).replace(' ML', '')}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function BoardSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-16 w-80" />
      <div className="grid grid-cols-12 gap-4"><Skeleton className="col-span-12 h-48 lg:col-span-8" /><Skeleton className="col-span-12 h-48 lg:col-span-4" /></div>
      <Skeleton className="h-24" />
      <Panel><div className="space-y-3">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-10" />)}</div></Panel>
    </div>
  )
}
