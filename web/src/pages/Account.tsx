import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { KeyRound, LogOut, Loader2 } from 'lucide-react'
import { api, auth } from '../lib/api'
import { Badge, Button, PageHead, Panel } from '../components/ui'

export function LoginCard({ onDone }: { onDone?: () => void }) {
  const [id, setId] = useState(auth.id)
  const [key, setKey] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const qc = useQueryClient()
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true); setErr('')
    try {
      await api.login(id.trim(), key.trim())
      auth.set(id.trim(), key.trim())
      await qc.invalidateQueries()
      onDone?.()
    } catch (x) { setErr(String((x as Error).message || x)) } finally { setBusy(false) }
  }
  return (
    <form onSubmit={submit} className="space-y-4">
      <label className="block">
        <span className="eyebrow mb-1.5 block">Email</span>
        <input value={id} onChange={(e) => setId(e.target.value)} autoComplete="username" className="h-10 w-full rounded-sm border border-line bg-ink-1 px-3 text-sm text-fog-1 focus:border-volt/60 focus:outline-none" />
      </label>
      <label className="block">
        <span className="eyebrow mb-1.5 block">License key</span>
        <input value={key} onChange={(e) => setKey(e.target.value.toUpperCase())} placeholder="XXXX-XXXX-XXXX-XXXX-XXXX" autoComplete="current-password"
          className="num h-10 w-full rounded-sm border border-line bg-ink-1 px-3 text-sm tracking-[.12em] text-fog-1 placeholder:text-fog-4 focus:border-volt/60 focus:outline-none" />
      </label>
      {err && <div className="rounded-sm border border-loss/30 bg-loss/8 px-3 py-2 text-xs text-loss">{err}</div>}
      <Button variant="primary" className="w-full" disabled={busy || !id || !key}>{busy ? <Loader2 size={15} className="animate-spin" /> : <KeyRound size={14} />}Activate</Button>
    </form>
  )
}

export function Account() {
  const { data: info } = useQuery({ queryKey: ['info'], queryFn: api.info })
  const { data: prof, error } = useQuery({ queryKey: ['profile', auth.key], queryFn: api.profile, enabled: !!auth.key, retry: false })
  const qc = useQueryClient()
  return (
    <>
      <PageHead kicker="Signed license · start and end date" title={<>Your <span className="text-volt">License</span></>} />
      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 lg:col-span-5" kicker="Status" title={prof ? prof.identifier : 'Not signed in'}>
          {prof ? (
            <div className="space-y-4">
              <div className="flex items-center gap-2"><Badge tone={prof.license_valid ? 'volt' : 'loss'}>{prof.license_valid ? 'Active' : 'Inactive'}</Badge><span className="text-xs text-fog-3">{prof.license_message}</span></div>
              <dl className="space-y-2.5 text-sm">
                {[['Plan', prof.plan], ['Role', prof.role], ['Valid until', prof.key_end_date?.slice(0, 10)], ['Devices', `${prof.devices} of ${prof.max_devices}`]].map(([k, v]) => (
                  <div key={k} className="flex justify-between border-b border-line pb-2.5 last:border-0"><dt className="text-fog-3">{k}</dt><dd className="num text-fog-1">{v}</dd></div>
                ))}
              </dl>
              <Button variant="outline" onClick={() => { auth.clear(); qc.invalidateQueries() }}><LogOut size={14} />Sign out</Button>
            </div>
          ) : (
            <>
              {error && <div className="mb-4 text-xs text-loss">{String((error as Error).message)}</div>}
              <LoginCard />
            </>
          )}
        </Panel>
        <Panel className="col-span-12 lg:col-span-7" kicker="How licensing works" title="Owner-issued, tamper-proof">
          <ul className="space-y-3 text-sm leading-relaxed text-fog-2">
            <li>Each license has a start and an end date. Outside that range the app does not run.</li>
            <li>The desktop app receives a token signed by the server's private key and checks it with the public key it ships with. A public key can verify a license but cannot make one, so editing the token or the app's files breaks it.</li>
            <li>Licenses are bound to a device limit and refresh on each online start, so a revoked or shortened license stops working. A clock set backwards is detected.</li>
            <li>Only the owner can create, extend or disable licenses (admin token, command line or the admin API).</li>
          </ul>
          <div className="mt-4 text-xs text-fog-3">This server {info?.require_login ? <span className="text-volt">requires a license for every page</span> : 'runs in open mode (local install); set REQUIRE_API_KEY=true for a hosted deployment'}.</div>
        </Panel>
      </div>
    </>
  )
}
