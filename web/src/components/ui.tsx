import clsx from 'clsx'
import type { ReactNode, ButtonHTMLAttributes } from 'react'

export function Panel({ title, kicker, actions, children, className, pad = true }:
  { title?: ReactNode; kicker?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; pad?: boolean }) {
  return (
    <section className={clsx('panel relative min-w-0', className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
          <div className="flex min-w-0 items-baseline gap-2.5">
            {kicker && <span className="eyebrow">{kicker}</span>}
            {title && <h3 className="truncate text-sm font-medium text-fog-1">{title}</h3>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
        </header>
      )}
      <div className={clsx(pad && 'p-4')}>{children}</div>
    </section>
  )
}

export function Stat({ label, value, sub, tone, size = 'md' }: { label: ReactNode; value: ReactNode; sub?: ReactNode; tone?: string; size?: 'sm' | 'md' | 'lg' }) {
  return (
    <div className="min-w-0">
      <div className="eyebrow mb-1.5 truncate">{label}</div>
      <div className={clsx('display', tone ?? 'text-fog-1', size === 'lg' ? 'text-[56px]' : size === 'md' ? 'text-[34px]' : 'text-[24px]')}>{value}</div>
      {sub && <div className="mt-1.5 truncate text-xs text-fog-3">{sub}</div>}
    </div>
  )
}

export function Badge({ children, tone = 'muted', className }: { children: ReactNode; tone?: 'volt' | 'ember' | 'loss' | 'muted' | 'ice' | 'gold'; className?: string }) {
  const t = {
    volt: 'text-volt border-volt/30 bg-volt/8',
    ember: 'text-ember border-ember/30 bg-ember/8',
    loss: 'text-loss border-loss/30 bg-loss/8',
    ice: 'text-ice border-ice/30 bg-ice/8',
    gold: 'text-gold border-gold/30 bg-gold/8',
    muted: 'text-fog-2 border-line-2 bg-ink-3',
  }[tone]
  return <span className={clsx('inline-flex h-5 items-center gap-1 rounded-xs border px-1.5 font-mono text-[10px] font-medium uppercase tracking-[.1em]', t, className)}>{children}</span>
}

export function Button({ children, variant = 'ghost', size = 'md', className, ...p }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'ghost' | 'outline'; size?: 'sm' | 'md' }) {
  return (
    <button {...p} className={clsx(
      'inline-flex select-none items-center justify-center gap-1.5 rounded-sm font-medium transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-40',
      size === 'sm' ? 'h-7 px-2.5 text-xs' : 'h-8.5 px-3.5 text-sm',
      variant === 'primary' && 'bg-volt text-ink-0 hover:bg-[#d6ff7a]',
      variant === 'outline' && 'border border-line-2 bg-ink-2 text-fog-1 hover:border-fog-4 hover:bg-ink-3',
      variant === 'ghost' && 'text-fog-2 hover:bg-ink-3 hover:text-fog-1',
      className)}>
      {children}
    </button>
  )
}

export function Seg<T extends string>({ value, options, onChange, className }: { value: T; options: { value: T; label: ReactNode }[]; onChange: (v: T) => void; className?: string }) {
  return (
    <div className={clsx('inline-flex rounded-sm border border-line bg-ink-1 p-0.5', className)}>
      {options.map((o) => (
        <button key={o.value} onClick={() => onChange(o.value)}
          className={clsx('h-6.5 rounded-xs px-2.5 font-mono text-[11px] uppercase tracking-[.08em] transition-colors',
            o.value === value ? 'bg-ink-4 text-fog-1' : 'text-fog-3 hover:text-fog-1')}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

/** Model probability against the price's break-even, on one track. The gap is the edge. */
export function ProbBar({ p, be, className }: { p: number | null; be: number; className?: string }) {
  const pp = p ?? be
  const lo = 0.2, hi = 0.9
  const x = (v: number) => `${Math.max(0, Math.min(1, (v - lo) / (hi - lo))) * 100}%`
  return (
    <div className={clsx('relative h-1.5 w-full rounded-full bg-ink-4', className)}>
      <div className="absolute inset-y-0 left-0 rounded-full bg-fog-4" style={{ width: x(be) }} />
      <div className="absolute inset-y-0 rounded-full bg-volt" style={{ left: x(be), width: `calc(${x(pp)} - ${x(be)})` }} />
      <div className="absolute -top-1 h-3.5 w-px bg-ember" style={{ left: x(be) }} />
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx('scan rounded-sm bg-ink-3', className)} />
}

export function Empty({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
      {icon && <div className="mb-1 text-fog-4">{icon}</div>}
      <div className="text-sm font-medium text-fog-1">{title}</div>
      {children && <div className="max-w-md text-xs leading-relaxed text-fog-3">{children}</div>}
    </div>
  )
}

export function Dot({ tone = 'volt', pulse }: { tone?: 'volt' | 'ember' | 'loss' | 'muted'; pulse?: boolean }) {
  const c = { volt: 'bg-volt', ember: 'bg-ember', loss: 'bg-loss', muted: 'bg-fog-4' }[tone]
  return <i className={clsx('inline-block h-1.5 w-1.5 shrink-0 rounded-full', c, pulse && 'pulse-dot')} />
}

export function PageHead({ kicker, title, children }: { kicker: string; title: ReactNode; children?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <div className="eyebrow mb-2 flex items-center gap-2"><span className="h-px w-5 bg-volt" />{kicker}</div>
        <h1 className="display text-[44px] text-fog-1 sm:text-[56px]">{title}</h1>
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  )
}
