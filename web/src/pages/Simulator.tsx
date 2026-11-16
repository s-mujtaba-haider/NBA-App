import { useEffect, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { Play, Loader2 } from 'lucide-react'
import { api, type MarketKey } from '../lib/api'
import { money, pctPlain, MARKET_HUE } from '../lib/format'
import { Button, PageHead, Panel, Seg, Stat } from '../components/ui'
import { FanChart, Histogram } from '../components/charts'

const ALL: MarketKey[] = ['totals', 'player_rebounds', 'player_threes', 'player_rebounds_assists', 'player_blocks', 'h2h']

export function Simulator() {
  const { data: sum } = useQuery({ queryKey: ['summary'], queryFn: api.summary })
  const [markets, setMarkets] = useState<MarketKey[]>(ALL)
  const [days, setDays] = useState(120)
  const [sims, setSims] = useState(5000)
  const [bankroll, setBankroll] = useState(100)
  const [stake, setStake] = useState(1)
  const [staking, setStaking] = useState<'flat' | 'percent'>('flat')
  const [haircut, setHaircut] = useState(0)
  const [pool, setPool] = useState<'all' | 'unseen'>('all')
  const run = useMutation({ mutationFn: () => api.simulate({ markets, days, sims, bankroll, stake, staking, haircut: haircut / 100, seasons: pool === 'unseen' ? ['2025-26', '2026-27'] : null }) })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { run.mutate() }, [])
  const r = run.data
  const toggle = (k: MarketKey) => setMarkets((m) => (m.includes(k) ? (m.length > 1 ? m.filter((x) => x !== k) : m) : [...m, k]))

  return (
    <>
      <PageHead kicker="Monte Carlo · whole nights resampled from the graded record" title={<>Bankroll <span className="text-volt">Simulator</span></>} />
      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 lg:col-span-4 xl:col-span-3" kicker="Inputs" title="Scenario">
          <div className="space-y-5">
            <div>
              <div className="eyebrow mb-2">Markets</div>
              <div className="grid grid-cols-2 gap-1.5">
                {ALL.map((k) => {
                  const m = sum?.markets.find((x) => x.key === k)
                  const on = markets.includes(k)
                  return (
                    <button key={k} onClick={() => toggle(k)} className={clsx('flex items-center gap-2 rounded-sm border px-2.5 py-2 text-left text-xs transition-colors',
                      on ? 'border-line-2 bg-ink-3 text-fog-1' : 'border-line bg-ink-1 text-fog-3 hover:text-fog-2')}>
                      <i className="h-2 w-2 rounded-full transition-opacity" style={{ background: MARKET_HUE[k], opacity: on ? 1 : .3 }} />
                      <span className="truncate">{m?.label ?? k}</span>
                    </button>
                  )
                })}
              </div>
            </div>
            <Range label="Horizon" value={days} set={setDays} min={20} max={300} step={10} fmt={(v) => `${v} pick days`} />
            <Range label="Simulations" value={sims} set={setSims} min={500} max={20000} step={500} fmt={(v) => v.toLocaleString()} />
            <Range label="Starting bankroll" value={bankroll} set={setBankroll} min={20} max={1000} step={10} fmt={(v) => `${v} units`} />
            <div>
              <div className="eyebrow mb-2">Staking</div>
              <Seg value={staking} onChange={(v) => { setStaking(v); setStake(v === 'flat' ? 1 : 1) }} options={[{ value: 'flat', label: 'Flat units' }, { value: 'percent', label: '% of bankroll' }]} />
            </div>
            <Range label={staking === 'flat' ? 'Stake per bet' : 'Stake per bet (% bankroll)'} value={stake} set={setStake} min={0.25} max={staking === 'flat' ? 5 : 5} step={0.25} fmt={(v) => staking === 'flat' ? `${v}u` : `${v}%`} />
            <Range label="Price haircut" value={haircut} set={setHaircut} min={0} max={5} step={0.5} fmt={(v) => v ? `payouts −${v}%` : 'none'} />
            <div>
              <div className="eyebrow mb-2">Sample</div>
              <Seg value={pool} onChange={setPool} options={[{ value: 'all', label: 'All seasons' }, { value: 'unseen', label: 'Unseen + live' }]} />
            </div>
            <Button variant="primary" className="w-full" onClick={() => run.mutate()} disabled={run.isPending}>
              {run.isPending ? <Loader2 size={15} className="animate-spin" /> : <Play size={14} />}Run {sims.toLocaleString()} simulations
            </Button>
            {run.error && <div className="text-xs text-loss">{String(run.error)}</div>}
          </div>
        </Panel>

        <div className="col-span-12 space-y-4 lg:col-span-8 xl:col-span-9">
          <div className={clsx('panel grid grid-cols-2 gap-6 p-5 md:grid-cols-4 xl:grid-cols-6 transition-opacity', run.isPending && 'opacity-50')}>
            <Stat label="Chance of profit" value={r ? pctPlain(r.prob_profit, 1) : '—'} tone="text-volt" size="lg" />
            <Stat label="Median end" value={r ? `${r.final.median.toFixed(0)}u` : '—'} sub={r ? `from ${r.bankroll}u` : ''} />
            <Stat label="Bad case (5%)" value={r ? `${r.final.p5.toFixed(0)}u` : '—'} />
            <Stat label="Good case (95%)" value={r ? `${r.final.p95.toFixed(0)}u` : '—'} />
            <Stat label="Drawdown p95" value={r ? `${r.drawdown_p95.toFixed(1)}u` : '—'} sub={r ? `median ${r.drawdown_median.toFixed(1)}u` : ''} />
            <Stat label="Lose 20%+" value={r ? pctPlain(r.prob_loss_20, 1) : '—'} tone={r && r.prob_loss_20 > .05 ? 'text-loss' : undefined} sub={r ? `ruin ${pctPlain(r.ruin, 2)}` : ''} />
          </div>
          <Panel kicker="Paths" title="Bankroll fan: 5-95% and 25-75% bands, median, 24 sample paths">
            {r ? <FanChart bands={r.bands} paths={r.sample_paths} base={r.bankroll} /> : <div className="h-[340px]" />}
          </Panel>
          <div className="grid grid-cols-12 gap-4">
            <Panel className="col-span-12 md:col-span-7" kicker="Outcome" title="Profit after the horizon (units)">
              {r && <Histogram counts={r.hist.counts} edges={r.hist.edges} />}
            </Panel>
            <Panel className="col-span-12 md:col-span-5" kicker="Sample" title="What the draw is made of">
              {r && (
                <dl className="space-y-2.5 text-xs">
                  {[['Pick days in the pool', r.pool_days.toLocaleString()], ['Graded bets in the pool', r.pool_bets.toLocaleString()],
                    ['Bets per pick day', r.bets_per_day.toFixed(1)], ['At $100 a unit, median', money((r.final.median - r.bankroll) * 100)],
                    ['Mean end', `${r.final.mean.toFixed(1)}u`]].map(([k, v]) => (
                    <div key={k} className="flex justify-between border-b border-line pb-2.5 last:border-0"><dt className="text-fog-3">{k}</dt><dd className="num text-fog-1">{v}</dd></div>
                  ))}
                </dl>
              )}
              <p className="mt-3 text-[11px] leading-relaxed text-fog-4">Resamples real nights, so it assumes the future looks like the record. It cannot know if the edge fades.</p>
            </Panel>
          </div>
        </div>
      </div>
    </>
  )
}

function Range({ label, value, set, min, max, step, fmt }: { label: string; value: number; set: (v: number) => void; min: number; max: number; step: number; fmt: (v: number) => string }) {
  return (
    <label className="block">
      <div className="mb-1.5 flex justify-between"><span className="eyebrow">{label}</span><span className="num text-xs text-fog-1">{fmt(value)}</span></div>
      <input type="range" className="w-full" min={min} max={max} step={step} value={value} onChange={(e) => set(Number(e.target.value))} />
    </label>
  )
}
