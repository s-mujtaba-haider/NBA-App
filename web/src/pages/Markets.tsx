import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { motion } from 'motion/react'
import { ArrowUpRight, ArrowLeft } from 'lucide-react'
import { api, type MarketSummary } from '../lib/api'
import { int, pct, pctPlain, units, MARKET_HUE, tone, odds } from '../lib/format'
import { Badge, PageHead, Panel, Skeleton, Stat } from '../components/ui'
import { Bars, Calibration, LineChart, Spark } from '../components/charts'
import { bookName } from './Board'

export function Markets() {
  const { data } = useQuery({ queryKey: ['summary'], queryFn: api.summary })
  return (
    <>
      <PageHead kicker="Two-Season Test · rule of record" title={<>Six <span className="text-volt">Winners</span></>} />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {data ? data.markets.map((m, i) => <MarketCard key={m.key} m={m} i={i} />) : Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-[300px]" />)}
      </div>
    </>
  )
}

function MarketCard({ m, i }: { m: MarketSummary; i: number }) {
  const c = MARKET_HUE[m.key]
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * .04, duration: .3 }}>
      <Link to={`/markets/${m.key}`} className="panel group relative block overflow-hidden transition-colors hover:border-line-2">
        <span className="absolute inset-x-0 top-0 h-px" style={{ background: `linear-gradient(90deg, ${c}, transparent 70%)` }} />
        <div className="flex items-start justify-between px-5 pt-5">
          <div>
            <div className="eyebrow flex items-center gap-2"><i className="h-1.5 w-1.5 rounded-full" style={{ background: c }} />{m.short} · {m.window}</div>
            <div className="mt-2 text-lg font-medium text-fog-1">{m.label}</div>
          </div>
          <div className="flex items-center gap-2">
            <Badge tone="volt">{m.status}</Badge>
            <ArrowUpRight size={16} className="text-fog-4 transition-colors group-hover:text-volt" />
          </div>
        </div>
        <div className="flex items-end justify-between gap-4 px-5 pt-4">
          <div>
            <div className="display text-[64px] text-fog-1">{pct(m.two_season.roi, 1)}</div>
            <div className="eyebrow mt-1.5">ROI · 2024-25 + 2025-26</div>
          </div>
          <div className="pb-1 text-right">
            <div className="num text-sm text-fog-1">{pct(m.two_season.ci_low)}</div>
            <div className="eyebrow mt-0.5">95% CI low</div>
          </div>
        </div>
        <div className="px-2 pt-3"><Spark data={m.spark} color={c} h={54} /></div>
        <div className="grid grid-cols-3 border-t border-line">
          {[['Bets', int(m.two_season.bets)], ['2025-26', pct(m.season_2025_26.roi)], ['Live', m.live.bets ? `${pct(m.live.roi)}` : '—']].map(([k, v], j) => (
            <div key={k} className={`px-5 py-3 ${j ? 'border-l border-line' : ''}`}>
              <div className="eyebrow !text-[9.5px]">{k}</div>
              <div className="num mt-0.5 text-sm text-fog-1">{v}</div>
            </div>
          ))}
        </div>
      </Link>
    </motion.div>
  )
}

export function MarketDetail() {
  const { key = 'totals' } = useParams()
  const { data: sum } = useQuery({ queryKey: ['summary'], queryFn: api.summary })
  const { data: eq } = useQuery({ queryKey: ['equity', key], queryFn: () => api.equity([key]) })
  const { data: mo } = useQuery({ queryKey: ['monthly'], queryFn: api.monthly })
  const { data: edge } = useQuery({ queryKey: ['edge', key], queryFn: () => api.edge(key) })
  const { data: recent } = useQuery({ queryKey: ['bets', key, 'recent'], queryFn: () => api.bets({ market: key, limit: 14 }) })
  const m = sum?.markets.find((x) => x.key === key)
  if (!m) return <Skeleton className="h-96" />
  const c = MARKET_HUE[key]
  const months = (mo?.rows ?? []).filter((r) => r.market === key)
  const firstLive = eq ? eq.season.indexOf('2026-27') : -1
  const first25 = eq ? eq.season.indexOf('2025-26') : -1
  return (
    <>
      <Link to="/markets" className="eyebrow mb-4 inline-flex items-center gap-1.5 hover:text-fog-1"><ArrowLeft size={12} />All markets</Link>
      <PageHead kicker={`${m.short} · window ${m.window}`} title={m.label}><Badge tone="volt">{m.status}</Badge></PageHead>

      <div className="panel mb-4 grid grid-cols-2 gap-6 p-5 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="ROI · 2 seasons" value={pct(m.two_season.roi)} tone="text-volt" />
        <Stat label="95% CI low" value={pct(m.two_season.ci_low)} />
        <Stat label="Bets" value={int(m.two_season.bets)} sub={`${m.two_season.won}-${m.two_season.lost}${m.two_season.push ? `-${m.two_season.push}` : ''}`} />
        <Stat label="Units" value={units(m.two_season.units, 0)} tone={tone(m.two_season.units)} />
        <Stat label="2025-26 ROI" value={pct(m.season_2025_26.roi)} sub={`${m.season_2025_26.bets} bets, unseen season`} />
        <Stat label="Live 2026-27" value={m.live.bets ? pct(m.live.roi) : '—'} tone={tone(m.live.roi)} sub={`${m.live.won}-${m.live.lost} · ${units(m.live.units)}`} />
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 xl:col-span-8" kicker="Units" title="Cumulative profit, flat 1u">
          {eq && <LineChart x={eq.dates} height={320} fmt={(v) => `${v.toFixed(0)}u`} xfmt={(s) => s.slice(0, 7)}
            bands={[...(first25 > 0 ? [{ from: first25, to: firstLive > 0 ? firstLive : eq.dates.length - 1, label: '2025-26' }] : []), ...(firstLive > 0 ? [{ from: firstLive, to: eq.dates.length - 1, label: 'LIVE' }] : [])]}
            series={[{ key, label: m.label, color: c, values: eq.series[key] ?? [], width: 2, fill: true }]} />}
        </Panel>
        <Panel className="col-span-12 xl:col-span-4" kicker="Rule" title="How it picks">
          <p className="text-sm leading-relaxed text-fog-2">{m.rule}.</p>
          <dl className="mt-4 space-y-2.5 text-xs">
            {[['Decision', m.window === '12:00 ET' ? '12:00 ET on game day' : `${m.window.replace('T-', '')} minutes before tip`], ['Price', 'Best of 8 US books at decision time'],
              ['Quotes', 'Stamped at or before the decision only'], ['Hit rate', pctPlain(m.two_season.hit_rate)], ['Median price', odds(m.two_season.avg_price)],
              ['Mean edge at pick', pct(m.two_season.avg_ev)]].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4 border-b border-line pb-2.5 last:border-0"><dt className="text-fog-3">{k}</dt><dd className="num text-right text-fog-1">{v}</dd></div>
            ))}
          </dl>
        </Panel>

        <Panel className="col-span-12 lg:col-span-7" kicker="By month" title="Units per month">
          <Bars labels={months.map((r) => r.month.slice(2))} values={months.map((r) => r.units)} color={c} />
        </Panel>
        <Panel className="col-span-12 lg:col-span-5" kicker="Edge" title="Realised ROI by edge at pick time">
          {edge && (() => {
            const b = edge.buckets.filter((x) => x.bets >= 20)
            return (
              <>
                <Bars labels={b.map((x) => x.bucket)} values={b.map((x) => (x.roi ?? 0) * 100)} color={c} fmt={(v) => `${v.toFixed(0)}%`} />
                <div className="num mt-2 flex justify-around text-[10.5px] text-fog-3">{b.map((x) => <span key={x.bucket}>n={x.bets}</span>)}</div>
              </>
            )
          })()}
        </Panel>

        <Panel className="col-span-12 lg:col-span-5" kicker="Calibration" title="Predicted vs actual win rate">
          {edge && <Calibration points={edge.calibration} />}
          <p className="mt-2 text-xs text-fog-3">Each dot is a probability bucket (size = bets). On the dashed line the model's probabilities match reality.</p>
        </Panel>
        <Panel className="col-span-12 lg:col-span-7" kicker="Latest" title="Recent picks" pad={false}>
          <table className="w-full text-sm">
            <tbody>
              {recent?.rows.map((b, i) => (
                <tr key={i} className="border-b border-line last:border-0">
                  <td className="num py-2 pl-4 text-xs text-fog-3">{b.slate}</td>
                  <td className="truncate py-2 text-fog-1">{b.who === 'GAME' ? 'Game' : b.who}</td>
                  <td className="num py-2 text-fog-2">{b.side.toUpperCase()} {b.point ?? ''}</td>
                  <td className="num py-2 text-fog-2">{odds(b.price)}</td>
                  <td className="hidden py-2 text-xs text-fog-3 sm:table-cell">{bookName(b.book)}</td>
                  <td className={`num py-2 pr-4 text-right ${tone(b.profit)}`}>{units(b.profit, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>
    </>
  )
}
