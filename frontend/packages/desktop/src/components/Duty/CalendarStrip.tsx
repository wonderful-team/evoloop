import { useMemo } from "react"

import type { QueueTask } from "@/lib/tasksQueueApi"

/** Week strip: task distribution across the current week (by due_at/updated). */
export function CalendarStrip({ tasks }: { tasks: QueueTask[] }) {
  const days = useMemo(() => {
    const now = new Date()
    const monday = new Date(now)
    monday.setDate(now.getDate() - ((now.getDay() + 6) % 7))
    monday.setHours(0, 0, 0, 0)
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(monday)
      d.setDate(monday.getDate() + i)
      const key = d.toISOString().slice(0, 10)
      const isToday = d.toDateString() === now.toDateString()
      const future = d > now
      const dayTasks = tasks.filter((t) => {
        const ref = t.due_at || t.last_thread_id ? t.due_at : null
        if (!ref) return false
        return new Date(ref).toISOString().slice(0, 10) === key
      })
      return { date: d, key, isToday, future, tasks: dayTasks }
    })
  }, [tasks])

  const labels = ["一", "二", "三", "四", "五", "六", "日"]

  return (
    <div className="grid grid-cols-7 gap-2">
      {days.map((d, i) => (
        <div
          key={d.key}
          className={`rounded-md p-2 min-h-[72px] ${
            d.isToday ? "bg-primary/10" : "bg-muted/30"
          } ${d.future ? "opacity-60" : ""}`}
        >
          <div className="text-[10px] text-muted-foreground flex items-center justify-between">
            <span>周{labels[i]}</span>
            <span>{d.date.getDate()}</span>
          </div>
          <div className="mt-1 space-y-0.5">
            {d.tasks.length === 0 ? (
              <div className="text-[10px] text-muted-foreground/40">—</div>
            ) : (
              d.tasks.slice(0, 3).map((t) => (
                <div
                  key={t.id}
                  className="text-[10px] truncate rounded px-1 py-0.5 bg-muted/60"
                  title={t.title ?? ""}
                >
                  {t.status === "completed" ? "✓" : t.status === "in_progress" ? "▶" : "○"}{" "}
                  {t.title}
                </div>
              ))
            )}
            {d.tasks.length > 3 && (
              <div className="text-[10px] text-muted-foreground">
                +{d.tasks.length - 3}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
