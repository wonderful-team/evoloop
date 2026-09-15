import { useEffect, useState } from "react"
import { DEMO } from "@/components/Duty/demoData"
import {
  getDemoDashboard,
  getDemoPulse,
} from "@/components/Duty/demoRuntime"
import { TasksQueueApi } from "@/lib/tasksQueueApi"

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
export function CostBlock() {
  const [cost, setCost] = useState({
    today: 0,
    week: 0,
    onDutySec: null as number | null,
  })

  useEffect(() => {
    let alive = true
    const iv = setInterval(async () => {
      if (!alive) return
      if (DEMO) {
        const d = getDemoDashboard()
        setCost({
          today: d.tokens.today.input + d.tokens.today.output,
          week: d.tokens.week.input + d.tokens.week.output,
          onDutySec: d.today_window.since
            ? Math.max(
                0,
                Math.floor(
                  (Date.now() - new Date(d.today_window.since).getTime()) /
                    1000,
                ),
              )
            : null,
        })
      } else {
        try {
          const d = await TasksQueueApi.dashboard()
          setCost({
            today:
              (d.tokens?.today?.input ?? 0) + (d.tokens?.today?.output ?? 0),
            week:
              (d.tokens?.week?.input ?? 0) + (d.tokens?.week?.output ?? 0),
            onDutySec: d.today_window?.since
              ? Math.max(
                  0,
                  Math.floor(
                    (Date.now() - new Date(d.today_window.since).getTime()) /
                      1000,
                  ),
                )
              : null,
          })
        } catch {
          /* keep last */
        }
      }
    }, 500)
    return () => {
      alive = false
      clearInterval(iv)
    }
  }, [])

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

/** Live waveform — execution-column aligned. */
export function PulseWave() {
  const [pulseData, setPulseData] = useState<number[]>([])

  useEffect(() => {
    let alive = true
    const iv = setInterval(async () => {
      if (!alive) return
      if (DEMO) {
        setPulseData(getDemoPulse())
      } else {
        try {
          const d = await TasksQueueApi.dashboard()
          setPulseData(
            (d.daily ?? []).map((x) => x.input_tokens + x.output_tokens),
          )
        } catch {
          /* keep last */
        }
      }
    }, 500)
    return () => {
      alive = false
      clearInterval(iv)
    }
  }, [])

  const max = Math.max(...pulseData, 1)

  return (
    <div className="rounded-lg bg-background px-3 pt-3 flex flex-col justify-end h-full">
      <div className="flex items-end gap-[3px] h-14 overflow-hidden">
        {pulseData.length === 0 ? (
          <div className="text-[10px] text-muted-foreground/50">
            {DEMO ? "等待启动…" : "数据接入中…"}
          </div>
        ) : (
          pulseData.map((v, i) => (
            <div
              key={i}
              className={`duty-bar flex-1 rounded-t-sm transition-all duration-500 origin-bottom ${
                i === pulseData.length - 1 ? "bg-primary" : "bg-primary/35"
              }`}
              style={{
                height: `${Math.max(8, (v / max) * 100)}%`,
                animation: `barBreath ${0.9 + ((i % 5) * 0.14)}s ease-in-out ${(i * 0.07) % 0.9}s infinite alternate`,
              }}
            />
          ))
        )}
      </div>

      <style>{`
        @keyframes barBreath {
          from { transform: scaleY(0.72); }
          to { transform: scaleY(1.08); }
        }
        @media (prefers-reduced-motion: reduce) {
          .duty-bar { animation: none !important; }
        }
      `}</style>
    </div>
  )
}
