import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import './index.css'
import { api, auth } from './lib/api'
import { Shell } from './components/Shell'
import { JobsProvider } from './components/jobs'
import { Board } from './pages/Board'
import { Markets, MarketDetail } from './pages/Markets'
import { Record } from './pages/Record'
import { Simulator } from './pages/Simulator'
import { History } from './pages/History'
import { Engine } from './pages/Engine'
import { Account, LoginCard } from './pages/Account'

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: 1 } } })

function Gate({ children }: { children: React.ReactNode }) {
  const { data: info } = useQuery({ queryKey: ['info'], queryFn: api.info })
  const { data: prof, isLoading } = useQuery({ queryKey: ['profile', auth.key], queryFn: api.profile, enabled: !!info?.require_login && !!auth.key, retry: false })
  if (!info) return <Splash />
  if (info.require_login && !prof) {
    if (isLoading && auth.key) return <Splash />
    return (
      <div className="canvas-grid grid min-h-full place-items-center p-6">
        <div className="w-full max-w-sm">
          <img src="/mark.svg" alt="" className="mb-6 h-12 w-12" />
          <div className="eyebrow mb-2">Baseline · NBA</div>
          <h1 className="display mb-6 text-[52px]">Sign <span className="text-volt">in</span></h1>
          <div className="panel p-5"><LoginCard /></div>
        </div>
      </div>
    )
  }
  return <>{children}</>
}

function Splash() {
  return (
    <div className="grid h-full place-items-center">
      <div className="flex flex-col items-center gap-4">
        <img src="/mark.svg" alt="" className="h-12 w-12 animate-pulse" />
        <div className="eyebrow">Loading the board</div>
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Gate>
          <JobsProvider>
            <Shell>
              <Routes>
                <Route path="/" element={<Board />} />
                <Route path="/day/:day" element={<Board />} />
                <Route path="/markets" element={<Markets />} />
                <Route path="/markets/:key" element={<MarketDetail />} />
                <Route path="/record" element={<Record />} />
                <Route path="/simulator" element={<Simulator />} />
                <Route path="/history" element={<History />} />
                <Route path="/engine" element={<Engine />} />
                <Route path="/account" element={<Account />} />
                <Route path="*" element={<Board />} />
              </Routes>
            </Shell>
          </JobsProvider>
        </Gate>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
