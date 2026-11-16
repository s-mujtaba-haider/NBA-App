import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, AlertTriangle, X, Info as InfoIcon } from 'lucide-react'
import { api, type Job } from '../lib/api'

interface Toast { id: number; title: string; body?: string; tone: 'ok' | 'err' | 'info'; to?: string }
interface Ctx {
  toast: (t: Omit<Toast, 'id'>) => void
  track: (jobId: string, label: string) => void
  running: Job[]
}
const C = createContext<Ctx>({ toast: () => {}, track: () => {}, running: [] })
export const useJobs = () => useContext(C)

let seq = 1

export function JobsProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const [running, setRunning] = useState<Job[]>([])
  const tracked = useRef(new Map<string, string>())
  const qc = useQueryClient()

  const toast = useCallback((t: Omit<Toast, 'id'>) => {
    const id = seq++
    setToasts((x) => [...x.slice(-3), { ...t, id }])
    setTimeout(() => setToasts((x) => x.filter((y) => y.id !== id)), 7000)
  }, [])

  const track = useCallback((jobId: string, label: string) => { tracked.current.set(jobId, label) }, [])

  useEffect(() => {
    const t = setInterval(async () => {
      if (!tracked.current.size) { setRunning([]); return }
      const jobs = await Promise.all([...tracked.current.keys()].map((id) => api.job(id).catch(() => null)))
      const live: Job[] = []
      for (const j of jobs) {
        if (!j) continue
        const label = tracked.current.get(j.job_id) || j.kind
        if (j.status === 'completed' || j.status === 'failed' || j.status === 'cancelled') {
          tracked.current.delete(j.job_id)
          toast({ title: j.status === 'completed' ? `${label} finished` : `${label} ${j.status}`, body: j.message, tone: j.status === 'completed' ? 'ok' : 'err', to: '/engine' })
          qc.invalidateQueries()
        } else live.push(j)
      }
      setRunning(live)
    }, 1200)
    return () => clearInterval(t)
  }, [qc, toast])

  return (
    <C.Provider value={{ toast, track, running }}>
      {children}
      <Toaster toasts={toasts} close={(id) => setToasts((x) => x.filter((y) => y.id !== id))} />
    </C.Provider>
  )
}

function Toaster({ toasts, close }: { toasts: Toast[]; close: (id: number) => void }) {
  const nav = useNavigate()
  return (
    <div className="pointer-events-none fixed right-4 bottom-12 z-50 flex w-[340px] max-w-[calc(100vw-32px)] flex-col gap-2">
      <AnimatePresence initial={false}>
        {toasts.map((t) => (
          <motion.div key={t.id} layout initial={{ opacity: 0, y: 12, scale: .98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, x: 24 }}
            transition={{ duration: .22, ease: [.2, .8, .2, 1] }}
            className="pointer-events-auto relative cursor-pointer overflow-hidden rounded-md border border-line-2 bg-ink-2/95 p-3 pr-8 shadow-[0_20px_50px_-20px_rgba(0,0,0,.8)] backdrop-blur"
            onClick={() => { if (t.to) nav(t.to); close(t.id) }}>
            <span className={`absolute inset-y-0 left-0 w-0.5 ${t.tone === 'ok' ? 'bg-volt' : t.tone === 'err' ? 'bg-loss' : 'bg-ice'}`} />
            <div className="flex items-start gap-2.5">
              {t.tone === 'ok' ? <CheckCircle2 size={16} className="mt-0.5 text-volt" /> : t.tone === 'err' ? <AlertTriangle size={16} className="mt-0.5 text-loss" /> : <InfoIcon size={16} className="mt-0.5 text-ice" />}
              <div className="min-w-0">
                <div className="text-sm font-medium text-fog-1">{t.title}</div>
                {t.body && <div className="mt-0.5 line-clamp-3 text-xs text-fog-3">{t.body}</div>}
                {t.to && <div className="eyebrow mt-1.5 text-volt-dim">View details →</div>}
              </div>
            </div>
            <button className="absolute top-2.5 right-2.5 text-fog-4 hover:text-fog-1" onClick={(e) => { e.stopPropagation(); close(t.id) }}><X size={14} /></button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}
