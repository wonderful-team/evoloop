import {useMemo} from "react"
import type {DashboardKpis} from "@/lib/tasksQueueApi"

function fmtK(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

function fmtDuty(sec: number): string {
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const ss = sec % 60
  return h > 0
    ? `${h}h ${String(m).padStart(2, "0")}m`
    : `${m}m ${String(ss).padStart(2, "0")}s`
}

/** Cost block — plan-column aligned: today / week / on-duty. */
export function CostBlock({
  dashboard,
  now,
}: {
  dashboard?: DashboardKpis
  now: number
}) {
  const cost = useMemo(() => {
    const today = dashboard?.tokens?.today
    const week = dashboard?.tokens?.week
    return {
      today: (today?.input ?? 0) + (today?.output ?? 0),
      week: (week?.input ?? 0) + (week?.output ?? 0),
      onDutySec: dashboard?.today_window?.since
        ? Math.max(
            0,
            Math.floor(
              (now - new Date(dashboard.today_window.since).getTime()) / 1000,
            ),
          )
        : null,
    }
  }, [dashboard, now])

  return (
    <div className="rounded-lg bg-background p-3 grid grid-cols-3 gap-2 items-center h-full">
      <div className="min-w-0">
        <div className="text-[10px] text-muted-foreground/70 mb-0.5 truncate">
          今日消耗
        </div>
        <div className="text-lg font-bold leading-none tracking-tight font-mono tabular-nums">
          {fmtK(cost.today)}
        </div>
      </div>
      <div className="min-w-0">
        <div className="text-[10px] text-muted-foreground/70 mb-0.5 truncate">
          本周累计
        </div>
        <div className="text-lg font-bold leading-none tracking-tight text-muted-foreground font-mono tabular-nums">
          {fmtK(cost.week)}
        </div>
      </div>
      <div className="min-w-0">
        <div className="text-[10px] text-muted-foreground/70 mb-0.5 truncate">
          在岗时长
        </div>
        <div className="text-lg font-bold leading-none tracking-tight font-mono tabular-nums">
          {cost.onDutySec === null ? (
            <span className="text-muted-foreground/40">—</span>
          ) : (
            fmtDuty(cost.onDutySec)
          )}
        </div>
      </div>
    </div>
  )
}

/** KITT scanner — back-and-forth sweep with a pause between passes
 *  (breathing rhythm): sweep out → sweep back → hold dark → repeat. */
const KITT_LEDS = 26
const KITT_PERIOD_S = 3.2 // sweep out + back + hold
const KITT_SWEET = 0.72 // fraction of period spent sweeping (rest = pause)

function pct(f: number): string {
  return `${Math.min(100, Math.max(0, Math.round(f * 1000)) / 10)}%`
}

function buildKittStyles(): string {
  const frames: string[] = []
  for (let i = 0; i < KITT_LEDS; i++) {
    // sweep window [0, KITT_SWEET]; pause window (KITT_SWEET, 1] stays dark
    const w = KITT_SWEET
    const out = (i / (KITT_LEDS - 1)) * 0.5 * w // outbound peak
    const back = w - out // return peak
    const glow = 0.05 * w // tail width (scaled inside sweep window)
    const stops: [number, string][] = [
      [0, "opacity: 0.05"],
      [
        out,
        "opacity: 1; box-shadow: 0 0 8px var(--destructive), 0 0 18px var(--destructive)",
      ],
      [
        Math.min(out + glow, w / 2),
        "opacity: 0.45; box-shadow: 0 0 4px var(--destructive)",
      ],
      [Math.max(out + glow + 0.02 * w, back - glow), "opacity: 0.05"],
      [
        back,
        "opacity: 1; box-shadow: 0 0 8px var(--destructive), 0 0 18px var(--destructive)",
      ],
      [
        Math.min(back + glow, w),
        "opacity: 0.45; box-shadow: 0 0 4px var(--destructive)",
      ],
      [1, "opacity: 0.05"],
    ]
    stops.sort((a, b) => a[0] - b[0])
    const body = stops
      .map(([pos, css]) => `${pct(pos)} { ${css} }`)
      .join(" ")
    frames.push(`@keyframes kitt-${i} { ${body} }`)
  }
  return frames.join("\n")
}

export function PulseWave({ active = false }: { active?: boolean }) {
  const styles = buildKittStyles()
  return (
    <div
      aria-hidden
      data-active={active}
      className="relative h-[2px] w-full overflow-hidden bg-border/30 shrink-0 select-none"
    >
      <div className="flex h-full w-full items-center gap-[2px]">
        {Array.from({ length: KITT_LEDS }).map((_, i) => (
          <span
            key={i}
            className="kitt-led flex-1"
            style={{
              animationName: `kitt-${i}`,
              animationDuration: `${KITT_PERIOD_S}s`,
              animationTimingFunction: "linear",
              animationIterationCount: "infinite",
            }}
          />
        ))}
      </div>
      <style>{`
        .kitt-led {
          height: 2px;
          opacity: 0.05;
          background: var(--destructive);
        }
        [data-active="false"] .kitt-led { opacity: 0.06; }
        [data-active="false"] .kitt-led { animation: none !important; }
        ${styles}
        @media (prefers-reduced-motion: reduce) {
          .kitt-led { animation: none !important; opacity: 0.3 !important; }
        }
      `}</style>
    </div>
  )
}
