import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { Zap, RefreshCcw, FlaskConical, ShieldCheck } from 'lucide-react'
import { api } from '../lib/api'
import { timeET } from '../lib/format'
import { Badge, Button, Dot, PageHead, Panel, Seg, Stat } from '../components/ui'
import { useJobs } from '../components/jobs'

export function Engine() {
  const { data } = useQuery({ queryKey: ['engine'], queryFn: api.engine, refetchInterval: 5000 })
  const { data: info } = useQuery({ queryKey: ['info'], queryFn: api.info })
  const [level, setLevel] = useState('all')
  const { data: logs } = useQuery({ queryKey: ['logs', level], queryFn: () => api.logs(level, 300), refetchInterval: 4000 })
  const { track, toast, running } = useJobs()
  const cr = (data?.credits ?? {}) as { configured?: boolean; registered?: boolean; status?: string; credits_spent?: number; max_credits?: number; requests_done?: number; max_requests?: number }

  const start = async (kind: 'picks' | 'results' | 'test', label: string) => {
    try {
      const { job_id } = await api.run(kind)
      track(job_id, label)
      toast({ title: `${label} started`, tone: 'info' })
    } catch (e) { toast({ title: `${label} failed to start`, body: String(e), tone: 'err' }) }
  }
  const busy = running.length > 0
  const now = Date.now()

  return (
    <>
      <PageHead kicker="Frozen rules · credit-gated odds feed" title={<>The <span className="text-volt">Engine</span></>} />
      <div className="grid grid-cols-12 gap-4">
        <div className="panel col-span-12 grid grid-cols-2 gap-6 p-5 md:grid-cols-4">
          <Stat label="Odds feed" value={cr.configured ? 'Online' : 'Offline'} tone={cr.configured ? 'text-volt' : 'text-fog-3'} sub={cr.configured ? 'client proxy' : 'set ODDS_API_BASE + token'} />
          <Stat label="Credits used" value={cr.registered ? `${cr.credits_spent ?? 0}` : '0'} sub={cr.max_credits ? `cap ${cr.max_credits.toLocaleString()} · ${cr.status}` : 'cap set on first run'} />
          <Stat label="Today's windows" value={data?.plan.decisions.length ?? '—'} sub={`about ${data?.plan.credits ?? 0} credits`} />
          <Stat label="Auto picks" value={info?.auto_picks ? 'On' : 'Manual'} tone={info?.auto_picks ? 'text-volt' : undefined} sub={info?.auto_picks ? 'runs every window' : 'press Run during a window'} />
        </div>

        <Panel className="col-span-12 lg:col-span-5" kicker="Controls" title="Run">
          <div className="space-y-3">
            <Action icon={<Zap size={16} />} title="Run due windows" desc="Fetch current odds for every decision window open right now and log picks. Billable: about 1-2 credits per window."
              onClick={() => start('picks', 'Pick run')} disabled={busy || !cr.configured} primary />
            <Action icon={<RefreshCcw size={16} />} title="Refresh results and grade" desc="Schedule and box scores from stats.nba.com, then grade every logged pick. Free."
              onClick={() => start('results', 'Results refresh')} disabled={busy} />
            <Action icon={<FlaskConical size={16} />} title="Test run on current odds" desc="Runs every unstarted game now, outside its window. Stored apart and never counted. Billable."
              onClick={() => start('test', 'Test run')} disabled={busy || !cr.configured} />
          </div>
          <div className="mt-4 flex items-start gap-2.5 rounded-sm border border-line bg-ink-1 p-3 text-xs leading-relaxed text-fog-3">
            <ShieldCheck size={15} className="mt-0.5 shrink-0 text-volt" />
            Every odds call passes the credit gate: an approval record with request and credit caps, no paid retries, a halt on any charge above the estimate, and a ledger line per call.
          </div>
        </Panel>

        <Panel className="col-span-12 lg:col-span-7" kicker={data?.plan.day} title="Decision plan" pad={false}>
          <div className="max-h-[360px] overflow-y-auto">
            {data?.plan.decisions.length ? data.plan.decisions.map((d) => {
              const t = new Date(d.at).getTime()
              const tick = data.ticks.find((x) => x.key === d.key) as { status?: string; picks?: number } | undefined
              const state = tick?.status ?? (now < t ? 'upcoming' : now < t + 600000 ? 'open' : 'closed')
              return (
                <div key={d.key} className="flex items-center gap-3 border-b border-line px-4 py-2 text-sm last:border-0">
                  <span className="num w-20 text-fog-1">{timeET(d.at)}</span>
                  <Badge tone={d.window === 'NOON' ? 'ice' : d.window.startsWith('T60') ? 'ember' : 'volt'}>{d.window}</Badge>
                  <span className="min-w-0 flex-1 truncate font-mono text-xs text-fog-3">{d.key.split('|')[1]}</span>
                  <span className={clsx('flex items-center gap-1.5 font-mono text-[11px] uppercase', state === 'ok' ? 'text-volt' : state === 'open' ? 'text-ember' : state === 'missed' ? 'text-loss' : 'text-fog-3')}>
                    <Dot tone={state === 'ok' ? 'volt' : state === 'open' ? 'ember' : state === 'missed' ? 'loss' : 'muted'} pulse={state === 'open'} />
                    {state}{tick?.picks ? ` · ${tick.picks}` : ''}
                  </span>
                </div>
              )
            }) : <div className="px-4 py-10 text-center text-sm text-fog-3">No games today.</div>}
          </div>
        </Panel>

        <Panel className="col-span-12 lg:col-span-5" kicker="Jobs" title="Recent runs" pad={false}>
          {(data?.jobs ?? []).length ? data!.jobs.map((j) => (
            <div key={j.job_id} className="border-b border-line px-4 py-2.5 last:border-0">
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm text-fog-1 capitalize">{j.kind}</span>
                <Badge tone={j.status === 'completed' ? 'volt' : j.status === 'failed' ? 'loss' : 'ember'}>{j.status}</Badge>
              </div>
              {j.status === 'running' && <div className="mt-2 h-1 overflow-hidden rounded-full bg-ink-4"><div className="h-full bg-volt" style={{ width: `${j.progress * 100}%` }} /></div>}
              <div className="mt-1 truncate text-xs text-fog-3">{j.message}</div>
              <div className="num mt-0.5 text-[10.5px] text-fog-4">{j.created_at?.replace('T', ' ').slice(0, 19)} UTC</div>
            </div>
          )) : <div className="px-4 py-10 text-center text-sm text-fog-3">No runs yet.</div>}
        </Panel>

        <Panel className="col-span-12 lg:col-span-7" kicker="Console" title="Logs" pad={false}
          actions={<Seg value={level} onChange={setLevel} options={[{ value: 'all', label: 'All' }, { value: 'warning', label: 'Warn' }, { value: 'error', label: 'Error' }]} />}>
          <div className="h-[340px] overflow-y-auto bg-[#050607] px-3 py-2 font-mono text-[11px] leading-[18px]">
            {(logs?.logs ?? []).map((l, i) => (
              <div key={i} className="flex gap-3 whitespace-nowrap">
                <span className="text-fog-4">{l.timestamp.slice(11, 19)}</span>
                <span className={clsx('w-14', l.level === 'ERROR' ? 'text-loss' : l.level === 'WARNING' ? 'text-gold' : 'text-fog-3')}>{l.level}</span>
                <span className="truncate text-fog-2">{l.message}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </>
  )
}

function Action({ icon, title, desc, onClick, disabled, primary }: { icon: React.ReactNode; title: string; desc: string; onClick: () => void; disabled?: boolean; primary?: boolean }) {
  return (
    <div className="flex items-center gap-4 rounded-sm border border-line bg-ink-1 p-3">
      <div className={clsx('grid h-9 w-9 shrink-0 place-items-center rounded-sm', primary ? 'bg-volt/10 text-volt' : 'bg-ink-3 text-fog-2')}>{icon}</div>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-fog-1">{title}</div>
        <div className="mt-0.5 text-xs leading-relaxed text-fog-3">{desc}</div>
      </div>
      <Button variant={primary ? 'primary' : 'outline'} size="sm" onClick={onClick} disabled={disabled}>Run</Button>
    </div>
  )
}
