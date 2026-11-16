import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { FileDown } from 'lucide-react'
import { api, download } from '../lib/api'
import { int, money, pct, units, MARKET_HUE, tone } from '../lib/format'
import { Button, PageHead, Panel, Seg, Skeleton, Stat } from '../components/ui'
import { LineChart, type Series } from '../components/charts'
import { useJobs } from '../components/jobs'
import { bookName } from './Board'

export function Record() {
  const { data: sum } = useQuery({ queryKey: ['summary'], queryFn: api.summary })
  const { data: eq } = useQuery({ queryKey: ['equity', 'all'], queryFn: () => api.equity() })
  const { data: mo } = useQuery({ queryKey: ['monthly'], queryFn: api.monthly })
  const { data: books } = useQuery({ queryKey: ['books'], queryFn: api.books })
  const { data: info } = useQuery({ queryKey: ['info'], queryFn: api.info })
  const [view, setView] = useState<'total' | 'split'>('total')
  const { toast } = useJobs()

  const series: Series[] = useMemo(() => {
    if (!eq || !sum) return []
    if (view === 'total') return [{ key: 'total', label: 'All six', color: '#c8f560', values: eq.total, width: 2.2, fill: true }]
    return sum.markets.map((m) => ({ key: m.key, label: m.short, color: MARKET_HUE[m.key], values: eq.series[m.key] ?? [], width: 1.6 }))
  }, [eq, sum, view])

  if (!sum) return <Skeleton className="h-96" />
  const t = sum.totals, s5 = t.season_2025_26
  const bands = eq ? [
    { from: 0, to: eq.season.indexOf('2025-26'), label: '2024-25' },
    { from: eq.season.indexOf('2025-26'), to: Math.max(eq.season.indexOf('2026-27'), 0) || eq.dates.length - 1, label: '2025-26 · UNSEEN' },
    ...(eq.season.indexOf('2026-27') > 0 ? [{ from: eq.season.indexOf('2026-27'), to: eq.dates.length - 1, label: 'LIVE' }] : []),
  ] : []

  const months = [...new Set((mo?.rows ?? []).map((r) => r.month))].sort()
  const cell = (k: string, month: string) => mo?.rows.find((r) => r.market === k && r.month === month)

  return (
    <>
      <PageHead kicker="Graded at the best price at pick time · flat 1 unit" title={<>Track <span className="text-volt">Record</span></>}>
        <Button variant="outline" size="sm" onClick={async () => { try { toast({ title: 'Report ready', body: await download('/api/export/report.pdf'), tone: 'ok' }) } catch (e) { toast({ title: 'Export failed', body: String(e), tone: 'err' }) } }}>
          <FileDown size={14} />Report PDF
        </Button>
      </PageHead>

      <div className="grid grid-cols-12 gap-4">
        <div className="panel col-span-12 grid grid-cols-2 gap-6 p-5 sm:grid-cols-4 xl:col-span-12 xl:grid-cols-7">
          <Stat label="2025-26 ROI" value={pct(s5.roi)} tone="text-volt" size="lg" sub="unseen season" />
          <Stat label="Units 25-26" value={units(s5.units, 0)} tone={tone(s5.units)} sub={`${money(s5.units * 100)} at $100 a bet`} />
          <Stat label="Bets 25-26" value={int(s5.bets)} sub={`${s5.bets_per_day} per pick day`} />
          <Stat label="Months green" value={`${s5.months_profit}/${s5.months}`} sub="2025-26" />
          <Stat label="Worst drop" value={`${s5.worst_drop.toFixed(1)}u`} sub="peak to trough" />
          <Stat label="Two seasons" value={pct(t.two_season.roi)} sub={`${int(t.two_season.bets)} bets · ${units(t.two_season.units, 0)}`} />
          <Stat label="Live 26-27" value={pct(t.live.roi)} tone={tone(t.live.roi)} sub={`${t.live.won}-${t.live.lost} · through ${t.live_last_slate?.slice(5) ?? '—'}`} />
        </div>

        <Panel className="col-span-12" kicker="Equity" title="Cumulative units since 2024-25"
          actions={<Seg value={view} onChange={setView} options={[{ value: 'total', label: 'Combined' }, { value: 'split', label: 'By market' }]} />}>
          {eq && <LineChart x={eq.dates} series={series} bands={bands} height={360} fmt={(v) => `${v.toFixed(0)}u`} xfmt={(s) => s.slice(0, 7)} />}
          {view === 'split' && (
            <div className="mt-3 flex flex-wrap gap-4">
              {sum.markets.map((m) => <span key={m.key} className="flex items-center gap-1.5 font-mono text-[11px] text-fog-2"><i className="h-1.5 w-3 rounded-full" style={{ background: MARKET_HUE[m.key] }} />{m.label}</span>)}
            </div>
          )}
        </Panel>

        <Panel className="col-span-12" kicker="Heatmap" title="Units by market and month" pad={false}>
          <div className="overflow-x-auto">
            <table className="w-full border-separate border-spacing-0 text-xs">
              <thead>
                <tr>
                  <th className="eyebrow sticky left-0 z-10 bg-ink-2 px-4 py-2 text-left font-normal">Market</th>
                  {months.map((m) => <th key={m} className="num px-1 py-2 text-center text-[10px] font-normal text-fog-3">{m.slice(2).replace('-', '/')}</th>)}
                </tr>
              </thead>
              <tbody>
                {sum.markets.map((mk) => (
                  <tr key={mk.key}>
                    <td className="sticky left-0 z-10 bg-ink-2 px-4 py-1 whitespace-nowrap text-fog-2"><span className="mr-2 inline-block h-1.5 w-1.5 rounded-full" style={{ background: MARKET_HUE[mk.key] }} />{mk.short}</td>
                    {months.map((m) => {
                      const c = cell(mk.key, m)
                      const v = c?.units ?? 0
                      const a = Math.min(Math.abs(v) / 15, 1)
                      return (
                        <td key={m} className="p-0.5">
                          <div title={c ? `${mk.label} ${m}: ${units(v)} over ${c.bets} bets` : 'no bets'}
                            className={clsx('num grid h-8 min-w-11 place-items-center rounded-xs text-[10px]', !c && 'text-fog-4')}
                            style={{ background: c ? (v >= 0 ? `rgba(200,245,96,${.06 + a * .5})` : `rgba(255,84,112,${.06 + a * .5})`) : 'rgba(255,255,255,.02)', color: c && a > .55 ? '#07080a' : undefined }}>
                            {c ? v.toFixed(1) : '·'}
                          </div>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel className="col-span-12 lg:col-span-7" kicker="Books" title="Where the best price was" pad={false}>
          <table className="w-full text-sm">
            <thead><tr className="border-b border-line">{['Book', 'Bets', 'Hit rate', 'Units', 'ROI'].map((h, i) => <th key={h} className={clsx('eyebrow px-4 py-2 font-normal', i ? 'text-right' : 'text-left')}>{h}</th>)}</tr></thead>
            <tbody>
              {books?.slice().sort((a, b) => b.bets - a.bets).map((b) => (
                <tr key={b.book} className="border-b border-line last:border-0">
                  <td className="px-4 py-2 text-fog-1">{bookName(b.book)}</td>
                  <td className="num px-4 py-2 text-right text-fog-2">{int(b.bets)}</td>
                  <td className="num px-4 py-2 text-right text-fog-2">{pct(b.hit_rate, 1, false)}</td>
                  <td className={`num px-4 py-2 text-right ${tone(b.units)}`}>{units(b.units)}</td>
                  <td className={`num px-4 py-2 text-right ${tone(b.roi)}`}>{pct(b.roi)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel className="col-span-12 lg:col-span-5" kicker="Read this" title={info?.rule.name ?? 'Rule of record'}>
          <p className="text-sm leading-relaxed text-fog-1">{info?.rule.definition}.</p>
          <ul className="mt-4 space-y-2.5">
            {info?.rule.disclosure.map((d) => (
              <li key={d} className="flex gap-2.5 text-xs leading-relaxed text-fog-3"><span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-ember" />{d}</li>
            ))}
          </ul>
        </Panel>
      </div>
    </>
  )
}
