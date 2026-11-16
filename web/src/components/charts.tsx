import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { scaleLinear, scaleBand } from 'd3-scale'
import { area, line, curveMonotoneX } from 'd3-shape'
import { extent, max, min } from 'd3-array'

export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [w, setW] = useState(0)
  useLayoutEffect(() => {
    if (!ref.current) return
    setW(Math.floor(ref.current.getBoundingClientRect().width))
    const ro = new ResizeObserver(([e]) => setW(Math.floor(e.contentRect.width)))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  return [ref, w] as const
}

const AXIS = '#444c56'
const GRID = 'rgba(255,255,255,0.05)'

/* ---------------------------------------------------------------- sparkline */
export function Spark({ data, color = '#c8f560', h = 36, fill = true }: { data: number[]; color?: string; h?: number; fill?: boolean }) {
  const [ref, w] = useWidth<HTMLDivElement>()
  const id = useMemo(() => `sp${Math.random().toString(36).slice(2, 8)}`, [])
  const d = data.length ? data : [0]
  const x = scaleLinear().domain([0, Math.max(d.length - 1, 1)]).range([1, Math.max(w - 1, 2)])
  const [lo, hi] = [Math.min(0, min(d) ?? 0), Math.max(0, max(d) ?? 0)]
  const y = scaleLinear().domain([lo, hi || 1]).range([h - 2, 2])
  const ln = line<number>().x((_, i) => x(i)).y((v) => y(v)).curve(curveMonotoneX)
  const ar = area<number>().x((_, i) => x(i)).y0(y(0)).y1((v) => y(v)).curve(curveMonotoneX)
  return (
    <div ref={ref} style={{ height: h }}>
      {w > 0 && (
        <svg width={w} height={h} className="block overflow-visible">
          <defs>
            <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor={color} stopOpacity=".28" />
              <stop offset="1" stopColor={color} stopOpacity="0" />
            </linearGradient>
          </defs>
          <line x1={0} x2={w} y1={y(0)} y2={y(0)} stroke={AXIS} strokeDasharray="2 3" />
          {fill && <path d={ar(d) || ''} fill={`url(#${id})`} />}
          <path d={ln(d) || ''} fill="none" stroke={color} strokeWidth={1.5} />
          <circle cx={x(d.length - 1)} cy={y(d[d.length - 1])} r={2.5} fill={color} />
        </svg>
      )}
    </div>
  )
}

/* ---------------------------------------------------------------- multi-line equity */
export interface Series { key: string; label: string; color: string; values: number[]; width?: number; fill?: boolean }

export function LineChart({ x, series, height = 300, bands, fmt = (v: number) => v.toFixed(1), xfmt = (s: string) => s }:
  { x: string[]; series: Series[]; height?: number; bands?: { from: number; to: number; label: string }[]; fmt?: (v: number) => string; xfmt?: (s: string) => string }) {
  const [ref, w] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const m = { t: 18, r: 56, b: 26, l: 8 }
  const iw = Math.max(w - m.l - m.r, 10), ih = height - m.t - m.b
  const all = series.flatMap((s) => s.values)
  const [lo, hi] = extent([0, ...all]) as [number, number]
  const xs = scaleLinear().domain([0, Math.max(x.length - 1, 1)]).range([0, iw])
  const ys = scaleLinear().domain([lo, hi]).nice(5).range([ih, 0])
  const ticks = ys.ticks(5)
  const xt = x.length ? [0, Math.floor(x.length * .25), Math.floor(x.length * .5), Math.floor(x.length * .75), x.length - 1] : []
  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const r = (e.currentTarget as SVGRectElement).getBoundingClientRect()
    const i = Math.round(xs.invert(e.clientX - r.left))
    setHover(Math.max(0, Math.min(x.length - 1, i)))
  }
  return (
    <div ref={ref} className="relative" style={{ height }}>
      {w > 0 && (
        <svg width={w} height={height} className="block">
          <defs>
            {series.filter((s) => s.fill).map((s) => (
              <linearGradient key={s.key} id={`lg-${s.key}`} x1="0" x2="0" y1="0" y2="1">
                <stop offset="0" stopColor={s.color} stopOpacity=".22" />
                <stop offset="1" stopColor={s.color} stopOpacity="0" />
              </linearGradient>
            ))}
          </defs>
          <g transform={`translate(${m.l},${m.t})`}>
            {bands?.map((b) => (
              <g key={b.label}>
                <rect x={xs(b.from)} width={Math.max(xs(b.to) - xs(b.from), 0)} y={0} height={ih} fill="rgba(255,255,255,0.018)" />
                <line x1={xs(b.from)} x2={xs(b.from)} y1={0} y2={ih} stroke={GRID} />
                <text x={xs(b.from) + 6} y={10} className="fill-fog-3" style={{ font: '500 10px var(--font-mono)', letterSpacing: '.12em' }}>{b.label}</text>
              </g>
            ))}
            {ticks.map((t) => (
              <g key={t}>
                <line x1={0} x2={iw} y1={ys(t)} y2={ys(t)} stroke={t === 0 ? AXIS : GRID} strokeDasharray={t === 0 ? '3 3' : undefined} />
                <text x={iw + 8} y={ys(t) + 3.5} className="fill-fog-3" style={{ font: '10.5px var(--font-mono)' }}>{fmt(t)}</text>
              </g>
            ))}
            {xt.map((i) => (
              <text key={i} x={xs(i)} y={ih + 18} textAnchor={i === 0 ? 'start' : i === x.length - 1 ? 'end' : 'middle'} className="fill-fog-3" style={{ font: '10.5px var(--font-mono)' }}>{xfmt(x[i])}</text>
            ))}
            {series.map((s) => {
              const ln = line<number>().x((_, i) => xs(i)).y((v) => ys(v)).curve(curveMonotoneX)
              const ar = area<number>().x((_, i) => xs(i)).y0(ys(Math.max(lo, 0))).y1((v) => ys(v)).curve(curveMonotoneX)
              return (
                <g key={s.key}>
                  {s.fill && <path d={ar(s.values) || ''} fill={`url(#lg-${s.key})`} />}
                  <path d={ln(s.values) || ''} fill="none" stroke={s.color} strokeWidth={s.width ?? 1.4} strokeLinejoin="round" />
                </g>
              )
            })}
            {hover != null && (
              <g>
                <line x1={xs(hover)} x2={xs(hover)} y1={0} y2={ih} stroke="rgba(255,255,255,.25)" />
                {series.map((s) => <circle key={s.key} cx={xs(hover)} cy={ys(s.values[hover] ?? 0)} r={3} fill={s.color} stroke="#07080a" strokeWidth={1.5} />)}
              </g>
            )}
            <rect width={iw} height={ih} fill="transparent" onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
          </g>
        </svg>
      )}
      {hover != null && w > 0 && (
        <div className="pointer-events-none absolute top-2 z-10 min-w-40 rounded-sm border border-line-2 bg-ink-1/95 px-3 py-2 shadow-2xl backdrop-blur"
          style={{ left: Math.min(m.l + xs(hover) + 12, w - 190) }}>
          <div className="eyebrow mb-1">{xfmt(x[hover])}</div>
          {series.map((s) => (
            <div key={s.key} className="flex items-center justify-between gap-4 text-xs">
              <span className="flex items-center gap-1.5 text-fog-2"><i className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: s.color }} />{s.label}</span>
              <span className="num text-fog-1">{fmt(s.values[hover] ?? 0)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ---------------------------------------------------------------- Monte Carlo fan */
export function FanChart({ bands, paths, base, height = 340 }:
  { bands: { day: number[]; p5: number[]; p25: number[]; p50: number[]; p75: number[]; p95: number[] }; paths: number[][]; base: number; height?: number }) {
  const [ref, w] = useWidth<HTMLDivElement>()
  const m = { t: 14, r: 58, b: 26, l: 8 }
  const iw = Math.max(w - m.l - m.r, 10), ih = height - m.t - m.b
  const all = [...bands.p5, ...bands.p95, base, ...paths.flat()]
  const xs = scaleLinear().domain([0, bands.day[bands.day.length - 1] || 1]).range([0, iw])
  const ys = scaleLinear().domain([min(all) ?? 0, max(all) ?? 1]).nice(6).range([ih, 0])
  const band = (lo: number[], hi: number[]) => area<number>().x((_, i) => xs(bands.day[i])).y0((_, i) => ys(lo[i])).y1((_, i) => ys(hi[i])).curve(curveMonotoneX)(lo) || ''
  const ln = (v: number[]) => line<number>().x((_, i) => xs(bands.day[i])).y((d) => ys(d)).curve(curveMonotoneX)(v) || ''
  const last = bands.day.length - 1
  return (
    <div ref={ref} style={{ height }}>
      {w > 0 && (
        <svg width={w} height={height} className="block">
          <g transform={`translate(${m.l},${m.t})`}>
            {ys.ticks(6).map((t) => (
              <g key={t}>
                <line x1={0} x2={iw} y1={ys(t)} y2={ys(t)} stroke={GRID} />
                <text x={iw + 8} y={ys(t) + 3.5} className="fill-fog-3" style={{ font: '10.5px var(--font-mono)' }}>{t}</text>
              </g>
            ))}
            {xs.ticks(6).map((t) => (
              <text key={t} x={xs(t)} y={ih + 18} textAnchor="middle" className="fill-fog-3" style={{ font: '10.5px var(--font-mono)' }}>D{t}</text>
            ))}
            {paths.map((p, i) => <path key={i} d={ln(p)} fill="none" stroke="rgba(169,177,187,.13)" strokeWidth={1} />)}
            <path d={band(bands.p5, bands.p95)} fill="rgba(200,245,96,.08)" />
            <path d={band(bands.p25, bands.p75)} fill="rgba(200,245,96,.16)" />
            <line x1={0} x2={iw} y1={ys(base)} y2={ys(base)} stroke="#ff6a2b" strokeDasharray="4 4" strokeOpacity=".7" />
            <path d={ln(bands.p50)} fill="none" stroke="#c8f560" strokeWidth={2} />
            {(['p95', 'p50', 'p5'] as const).map((k) => (
              <g key={k} transform={`translate(${xs(bands.day[last])},${ys(bands[k][last])})`}>
                <circle r={3} fill={k === 'p50' ? '#c8f560' : '#6b7480'} />
              </g>
            ))}
          </g>
        </svg>
      )}
    </div>
  )
}

/* ---------------------------------------------------------------- signed bars */
export function Bars({ labels, values, height = 200, color = '#c8f560', neg = '#ff5470', fmt = (v: number) => v.toFixed(1) }:
  { labels: string[]; values: number[]; height?: number; color?: string; neg?: string; fmt?: (v: number) => string }) {
  const [ref, w] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const m = { t: 16, r: 8, b: 24, l: 8 }
  const iw = Math.max(w - m.l - m.r, 10), ih = height - m.t - m.b
  const xs = scaleBand<number>().domain(labels.map((_, i) => i)).range([0, iw]).padding(0.28)
  const ys = scaleLinear().domain([Math.min(0, min(values) ?? 0), Math.max(0, max(values) ?? 1)]).nice(4).range([ih, 0])
  const every = Math.ceil(labels.length / Math.max(Math.floor(iw / 52), 1))
  return (
    <div ref={ref} style={{ height }}>
      {w > 0 && (
        <svg width={w} height={height} className="block">
          <g transform={`translate(${m.l},${m.t})`}>
            <line x1={0} x2={iw} y1={ys(0)} y2={ys(0)} stroke={AXIS} />
            {values.map((v, i) => (
              <g key={i} onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)}>
                <rect x={(xs(i) ?? 0) - 2} width={xs.bandwidth() + 4} y={0} height={ih} fill={hover === i ? 'rgba(255,255,255,.03)' : 'transparent'} />
                <rect x={xs(i)} width={xs.bandwidth()} y={Math.min(ys(v), ys(0))} height={Math.max(Math.abs(ys(v) - ys(0)), 1)}
                  fill={v >= 0 ? color : neg} opacity={hover == null || hover === i ? 0.95 : 0.45} rx={1.5} />
                {(hover === i || labels.length <= 14) && (
                  <text x={(xs(i) ?? 0) + xs.bandwidth() / 2} y={v >= 0 ? ys(v) - 5 : ys(v) + 12} textAnchor="middle"
                    className={v >= 0 ? 'fill-fog-1' : 'fill-loss'} style={{ font: '10px var(--font-mono)' }}>{fmt(v)}</text>
                )}
                {i % every === 0 && (
                  <text x={(xs(i) ?? 0) + xs.bandwidth() / 2} y={ih + 16} textAnchor="middle" className="fill-fog-3" style={{ font: '10px var(--font-mono)' }}>{labels[i]}</text>
                )}
              </g>
            ))}
          </g>
        </svg>
      )}
    </div>
  )
}

/* ---------------------------------------------------------------- histogram of outcomes */
export function Histogram({ counts, edges, height = 160 }: { counts: number[]; edges: number[]; height?: number }) {
  const [ref, w] = useWidth<HTMLDivElement>()
  const m = { t: 8, r: 8, b: 22, l: 8 }
  const iw = Math.max(w - m.l - m.r, 10), ih = height - m.t - m.b
  const xs = scaleLinear().domain([edges[0], edges[edges.length - 1]]).range([0, iw])
  const ys = scaleLinear().domain([0, max(counts) || 1]).range([ih, 0])
  return (
    <div ref={ref} style={{ height }}>
      {w > 0 && (
        <svg width={w} height={height} className="block">
          <g transform={`translate(${m.l},${m.t})`}>
            {counts.map((c, i) => (
              <rect key={i} x={xs(edges[i]) + 0.5} width={Math.max(xs(edges[i + 1]) - xs(edges[i]) - 1, 1)} y={ys(c)} height={ih - ys(c)}
                fill={edges[i + 1] <= 0 ? '#ff5470' : edges[i] >= 0 ? '#c8f560' : '#a9b1bb'} opacity={0.85} />
            ))}
            {edges[0] < 0 && edges[edges.length - 1] > 0 && <line x1={xs(0)} x2={xs(0)} y1={0} y2={ih} stroke="#ff6a2b" strokeDasharray="3 3" />}
            {xs.ticks(6).map((t) => (
              <text key={t} x={xs(t)} y={ih + 16} textAnchor="middle" className="fill-fog-3" style={{ font: '10px var(--font-mono)' }}>{t > 0 ? `+${t}` : t}</text>
            ))}
          </g>
        </svg>
      )}
    </div>
  )
}

/* ---------------------------------------------------------------- calibration */
export function Calibration({ points, height = 220 }: { points: { p: number; actual: number; n: number }[]; height?: number }) {
  const [ref, w] = useWidth<HTMLDivElement>()
  const m = { t: 10, r: 10, b: 26, l: 34 }
  const iw = Math.max(w - m.l - m.r, 10), ih = height - m.t - m.b
  const lo = Math.max(0, (min(points.map((p) => Math.min(p.p, p.actual))) ?? 0) - 0.05)
  const hi = Math.min(1, (max(points.map((p) => Math.max(p.p, p.actual))) ?? 1) + 0.05)
  const xs = scaleLinear().domain([lo, hi]).range([0, iw])
  const ys = scaleLinear().domain([lo, hi]).range([ih, 0])
  const r = scaleLinear().domain([0, max(points.map((p) => p.n)) || 1]).range([2.5, 9])
    return (
    <div ref={ref} style={{ height }}>
      {w > 0 && (
        <svg width={w} height={height} className="block">
          <g transform={`translate(${m.l},${m.t})`}>
            {xs.ticks(5).map((t) => (
              <g key={t}>
                <line x1={xs(t)} x2={xs(t)} y1={0} y2={ih} stroke={GRID} />
                <line x1={0} x2={iw} y1={ys(t)} y2={ys(t)} stroke={GRID} />
                <text x={xs(t)} y={ih + 16} textAnchor="middle" className="fill-fog-3" style={{ font: '10px var(--font-mono)' }}>{Math.round(t * 100)}</text>
                <text x={-6} y={ys(t) + 3} textAnchor="end" className="fill-fog-3" style={{ font: '10px var(--font-mono)' }}>{Math.round(t * 100)}</text>
              </g>
            ))}
            <line x1={xs(lo)} y1={ys(lo)} x2={xs(hi)} y2={ys(hi)} stroke="#ff6a2b" strokeDasharray="4 4" strokeOpacity=".6" />
            {points.map((p, i) => <circle key={i} cx={xs(p.p)} cy={ys(p.actual)} r={r(p.n)} fill="#c8f560" fillOpacity={0.75} stroke="#07080a" />)}
          </g>
        </svg>
      )}
    </div>
  )
}
