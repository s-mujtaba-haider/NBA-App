import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { Search, FileSpreadsheet, ChevronLeft, ChevronRight } from 'lucide-react'
import { api, download } from '../lib/api'
import { int, odds, pct, pctPlain, units, MARKET_HUE, tone } from '../lib/format'
import { Badge, Button, PageHead, Seg } from '../components/ui'
import { useJobs } from '../components/jobs'
import { bookName } from './Board'

const SHORT: Record<string, string> = { totals: 'TOT', player_rebounds: 'REB', player_threes: '3PM', player_rebounds_assists: 'R+A', player_blocks: 'BLK', h2h: 'ML' }
const PAGE = 50

export function History() {
  const [market, setMarket] = useState('')
  const [season, setSeason] = useState('')
  const [result, setResult] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(0)
  const { toast } = useJobs()
  const { data, isFetching } = useQuery({
    queryKey: ['bets', market, season, result, q, page],
    queryFn: () => api.bets({ market, season, result, q, limit: PAGE, offset: page * PAGE }),
    placeholderData: keepPreviousData,
  })
  const pages = data ? Math.ceil(data.total / PAGE) : 0
  const reset = <T,>(f: (v: T) => void) => (v: T) => { f(v); setPage(0) }

  return (
    <>
      <PageHead kicker="Every graded bet · 2024-25 to live" title={<>Bet <span className="text-volt">History</span></>}>
        <Button variant="outline" size="sm" onClick={async () => {
          try { toast({ title: 'Export ready', body: await download(`/api/export/bets.csv?${new URLSearchParams({ ...(market && { market }), ...(season && { season }) })}`), tone: 'ok' }) }
          catch (e) { toast({ title: 'Export failed', body: String(e), tone: 'err' }) }
        }}><FileSpreadsheet size={14} />Export CSV</Button>
      </PageHead>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search size={14} className="absolute top-1/2 left-2.5 -translate-y-1/2 text-fog-4" />
          <input value={q} onChange={(e) => reset(setQ)(e.target.value)} placeholder="Player or book"
            className="h-8 w-56 rounded-sm border border-line bg-ink-1 pr-3 pl-8 text-sm text-fog-1 placeholder:text-fog-4 focus:border-line-2 focus:outline-none" />
        </div>
        <Seg value={market} onChange={reset(setMarket)} options={[{ value: '', label: 'All' }, ...Object.entries(SHORT).map(([k, v]) => ({ value: k, label: v }))]} />
        <Seg value={season} onChange={reset(setSeason)} options={[{ value: '', label: 'All seasons' }, { value: '2024-25', label: '24-25' }, { value: '2025-26', label: '25-26' }, { value: '2026-27', label: 'Live' }]} />
        <Seg value={result} onChange={reset(setResult)} options={[{ value: '', label: 'Any' }, { value: 'won', label: 'Won' }, { value: 'lost', label: 'Lost' }]} />
        <span className={clsx('num ml-auto text-xs text-fog-3', isFetching && 'opacity-50')}>{int(data?.total)} bets</span>
      </div>

      <div className="panel overflow-x-auto">
        <table className="w-full min-w-[860px] text-sm">
          <thead>
            <tr className="border-b border-line">
              {['Date', 'Market', 'Selection', 'Side', 'Price', 'Book', 'Win prob', 'Edge', 'Result', 'Units'].map((h, i) => (
                <th key={h} className={clsx('eyebrow px-3 py-2.5 font-normal', i >= 6 ? 'text-right' : 'text-left', i === 0 && 'pl-4', i === 9 && 'pr-4')}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className={clsx(isFetching && 'opacity-60')}>
            {data?.rows.map((b, i) => (
              <tr key={i} className="border-b border-line transition-colors last:border-0 hover:bg-ink-3/50">
                <td className="num py-2 pl-4 text-xs text-fog-3">{b.slate}</td>
                <td className="px-3 py-2"><span className="flex items-center gap-1.5 font-mono text-[11px] text-fog-2"><i className="h-1.5 w-1.5 rounded-full" style={{ background: MARKET_HUE[b.market] }} />{SHORT[b.market]}</span></td>
                <td className="max-w-56 truncate px-3 py-2 text-fog-1">{b.who === 'GAME' ? <span className="text-fog-3">Game</span> : b.who}</td>
                <td className="num px-3 py-2 text-fog-2">{b.side.toUpperCase()} {b.point ?? ''}</td>
                <td className="num px-3 py-2 text-fog-1">{odds(b.price)}</td>
                <td className="px-3 py-2 text-xs text-fog-3">{bookName(b.book)}</td>
                <td className="num px-3 py-2 text-right text-fog-2">{pctPlain(b.p_win)}</td>
                <td className="num px-3 py-2 text-right text-volt/80">{pct(b.ev)}</td>
                <td className="px-3 py-2 text-right">{b.result > 0 ? <Badge tone="volt">Won</Badge> : b.result < 0 ? <Badge tone="loss">Lost</Badge> : <Badge>Push</Badge>}</td>
                <td className={`num py-2 pr-4 text-right ${tone(b.profit)}`}>{units(b.profit, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex items-center justify-end gap-2">
        <span className="num text-xs text-fog-3">page {page + 1} / {Math.max(pages, 1)}</span>
        <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}><ChevronLeft size={14} /></Button>
        <Button variant="outline" size="sm" disabled={page >= pages - 1} onClick={() => setPage((p) => p + 1)}><ChevronRight size={14} /></Button>
      </div>
    </>
  )
}
