import { useState, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'motion/react'
import clsx from 'clsx'
import { Radar, LayoutGrid, LineChart as LineIcon, Dices, Rows3, Cpu, KeyRound, ChevronUp, Terminal } from 'lucide-react'
import { api } from '../lib/api'
import { pct, units, MARKET_HUE } from '../lib/format'
import { useJobs } from './jobs'
import { Dot } from './ui'

const NAV = [
  { to: '/', label: 'Board', icon: Radar, end: true },
  { to: '/markets', label: 'Markets', icon: LayoutGrid },
  { to: '/record', label: 'Record', icon: LineIcon },
  { to: '/simulator', label: 'Simulator', icon: Dices },
  { to: '/history', label: 'History', icon: Rows3 },
  { to: '/engine', label: 'Engine', icon: Cpu },
]

function Mark() {
  return (
    <svg viewBox="0 0 64 64" className="h-7 w-7">
      <path d="M14 46h36" stroke="#C8F560" strokeWidth="5" strokeLinecap="round" />
      <path d="M18 40a14 14 0 0 1 28 0" fill="none" stroke="#C8F560" strokeWidth="5" strokeLinecap="round" />
      <circle cx="32" cy="22" r="4.5" fill="#FF6A2B" />
    </svg>
  )
}

function Rail() {
  return (
    <nav className="hidden w-[76px] shrink-0 flex-col items-center border-r border-line bg-ink-1 py-4 md:flex">
      <NavLink to="/" className="mb-6 flex flex-col items-center gap-1"><Mark /></NavLink>
      <div className="flex flex-1 flex-col gap-1">
        {NAV.map(({ to, label, icon: I, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => clsx(
            'group relative flex w-[60px] flex-col items-center gap-1 rounded-sm py-2.5 transition-colors',
            isActive ? 'text-fog-1' : 'text-fog-3 hover:text-fog-1')}>
            {({ isActive }) => (
              <>
                {isActive && <motion.span layoutId="rail" className="absolute inset-0 rounded-sm border border-line-2 bg-ink-3" transition={{ duration: .25, ease: [.2, .8, .2, 1] }} />}
                {isActive && <span className="absolute top-2 bottom-2 -left-2 w-0.5 rounded-full bg-volt" />}
                <I size={18} strokeWidth={1.6} className="relative" />
                <span className="relative font-mono text-[9.5px] tracking-[.08em] uppercase">{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </div>
      <NavLink to="/account" className={({ isActive }) => clsx('flex w-[60px] flex-col items-center gap-1 rounded-sm py-2.5', isActive ? 'text-fog-1' : 'text-fog-3 hover:text-fog-1')}>
        <KeyRound size={17} strokeWidth={1.6} />
        <span className="font-mono text-[9.5px] tracking-[.08em] uppercase">License</span>
      </NavLink>
    </nav>
  )
}

function MobileNav() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 flex border-t border-line bg-ink-1/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden">
      {NAV.map(({ to, label, icon: I, end }) => (
        <NavLink key={to} to={to} end={end} className={({ isActive }) => clsx('flex flex-1 flex-col items-center gap-0.5 py-2', isActive ? 'text-volt' : 'text-fog-3')}>
          <I size={18} strokeWidth={1.6} />
          <span className="font-mono text-[9px] tracking-[.06em] uppercase">{label}</span>
        </NavLink>
      ))}
    </nav>
  )
}

function Ticker() {
  const { data } = useQuery({ queryKey: ['summary'], queryFn: api.summary })
  if (!data) return <div className="h-9 border-b border-line bg-ink-1" />
  const items = data.markets.map((m) => (
    <span key={m.key} className="flex items-center gap-2 px-5">
      <i className="h-1.5 w-1.5 rounded-full" style={{ background: MARKET_HUE[m.key] }} />
      <span className="font-mono text-[11px] tracking-[.08em] text-fog-2 uppercase">{m.label}</span>
      <span className={clsx('num text-[11.5px]', (m.two_season.roi ?? 0) > 0 ? 'text-volt' : 'text-loss')}>{pct(m.two_season.roi)}</span>
      <span className="num text-[11px] text-fog-3">{m.two_season.bets.toLocaleString()} bets</span>
      <span className="text-fog-4">/</span>
    </span>
  ))
  const t = data.totals
  return (
    <div className="flex h-9 items-stretch border-b border-line bg-ink-1 text-xs">
      <div className="flex shrink-0 items-center gap-2 border-r border-line px-4">
        <Dot pulse />
        <span className="font-mono text-[11px] tracking-[.1em] text-fog-1 uppercase">{data.winners} winners</span>
        <span className="hidden font-mono text-[11px] text-fog-3 sm:inline">· live {units(t.live.units)} · {pct(t.live.roi)}</span>
      </div>
      <div className="relative min-w-0 flex-1 overflow-hidden [mask-image:linear-gradient(90deg,transparent,#000_6%,#000_94%,transparent)]">
        <div className="ticker-track absolute inset-y-0 flex w-max items-center">{items}{items}</div>
      </div>
    </div>
  )
}

function StatusBar({ onLogs, logsOpen }: { onLogs: () => void; logsOpen: boolean }) {
  const { running } = useJobs()
  const { data: info } = useQuery({ queryKey: ['info'], queryFn: api.info })
  const { data: eng } = useQuery({ queryKey: ['engine'], queryFn: api.engine, refetchInterval: 30000 })
  const cr = eng?.credits as { credits_spent?: number; max_credits?: number; configured?: boolean } | undefined
  const j = running[0]
  return (
    <footer className="hidden h-7 shrink-0 items-center gap-4 border-t border-line bg-ink-1 px-3 font-mono text-[10.5px] tracking-[.04em] text-fog-3 md:flex">
      <span className="flex items-center gap-1.5"><Dot tone="volt" />API online</span>
      <span className="flex items-center gap-1.5">
        <Dot tone={info?.odds_configured ? 'volt' : 'muted'} />Odds feed {info?.odds_configured ? 'connected' : 'not configured'}
      </span>
      {cr?.max_credits != null && <span>Credits {cr.credits_spent ?? 0}/{cr.max_credits}</span>}
      <span>Auto picks {info?.auto_picks ? 'on' : 'off'}</span>
      {j && (
        <span className="flex min-w-0 items-center gap-2 text-fog-1">
          <span className="truncate">{j.message || j.kind}</span>
          <span className="relative h-1 w-28 overflow-hidden rounded-full bg-ink-4"><span className="absolute inset-y-0 left-0 bg-volt transition-all" style={{ width: `${Math.max(4, j.progress * 100)}%` }} /></span>
          <span>{Math.round(j.progress * 100)}%{j.eta_seconds ? ` · ${Math.ceil(j.eta_seconds)}s left` : ''}</span>
        </span>
      )}
      <span className="ml-auto">v{info?.version}</span>
      <button onClick={onLogs} className={clsx('flex items-center gap-1 rounded-xs px-1.5 py-0.5 hover:bg-ink-3 hover:text-fog-1', logsOpen && 'bg-ink-3 text-fog-1')}>
        <Terminal size={12} /> Logs <ChevronUp size={12} className={clsx('transition-transform', logsOpen && 'rotate-180')} />
      </button>
    </footer>
  )
}

function LogDrawer({ open }: { open: boolean }) {
  const { data } = useQuery({ queryKey: ['logs-mini'], queryFn: () => api.logs('all', 120), refetchInterval: open ? 3000 : false, enabled: open })
  return (
    <AnimatePresence>
      {open && (
        <motion.div initial={{ height: 0 }} animate={{ height: 220 }} exit={{ height: 0 }} transition={{ duration: .22, ease: [.2, .8, .2, 1] }}
          className="hidden shrink-0 overflow-hidden border-t border-line bg-[#050607] md:block">
          <div className="h-full overflow-y-auto px-3 py-2 font-mono text-[11px] leading-[18px]">
            {(data?.logs ?? []).map((l, i) => (
              <div key={i} className="flex gap-3 whitespace-nowrap">
                <span className="text-fog-4">{l.timestamp.slice(11, 19)}</span>
                <span className={clsx('w-14', l.level === 'ERROR' ? 'text-loss' : l.level === 'WARNING' ? 'text-gold' : 'text-fog-3')}>{l.level}</span>
                <span className="w-20 truncate text-ice/70">{l.source}</span>
                <span className="truncate text-fog-2">{l.message}</span>
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export function Shell({ children }: { children: ReactNode }) {
  const [logs, setLogs] = useState(false)
  const loc = useLocation()
  return (
    <div className="flex h-full bg-ink-0">
      <Rail />
      <div className="flex min-w-0 flex-1 flex-col">
        <Ticker />
        <main className="canvas-grid relative min-h-0 flex-1 overflow-x-hidden overflow-y-auto">
          <AnimatePresence mode="wait">
            <motion.div key={loc.pathname} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
              transition={{ duration: .2, ease: [.2, .8, .2, 1] }} className="mx-auto w-full max-w-[1480px] px-4 pt-6 pb-24 sm:px-6 md:pb-10 lg:px-8">
              {children}
            </motion.div>
          </AnimatePresence>
        </main>
        <LogDrawer open={logs} />
        <StatusBar onLogs={() => setLogs((v) => !v)} logsOpen={logs} />
      </div>
      <MobileNav />
    </div>
  )
}
