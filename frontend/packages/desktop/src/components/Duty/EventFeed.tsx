import { useTranslation } from "react-i18next"

import type { DashboardKpis } from "@/lib/tasksQueueApi"

const KIND_META: Record<string, { icon: string; cls: string }> = {
  proposal: { icon: "➕", cls: "text-violet-600 dark:text-violet-400" },
  acceptance: { icon: "✓", cls: "text-green-600 dark:text-green-400" },
  progress: { icon: "▶", cls: "text-primary" },
}

/** Event stream feed — recently touched tasks, newest first, fade-in on change. */
export function EventFeed({
  events,
}: {
  events: DashboardKpis["recent_events"]
}) {
  const { t } = useTranslation()

  if (!events || events.length === 0) {
    return (
      <div className="text-xs text-muted-foreground px-1">
        {t("dutyBoard.feed.empty")}
      </div>
    )
  }

  return (
    <div className="space-y-1">
      {events.map((e, i) => {
        const meta = KIND_META[e.kind] ?? KIND_META.progress
        const time = e.at ? new Date(e.at).toLocaleTimeString() : ""
        return (
          <div
            key={`${e.task_id}-${e.at}-${i}`}
            className="flex items-baseline gap-2 text-xs py-1 border-b border-border/40 last:border-0 animate-in fade-in slide-in-from-bottom-1"
            style={{ animationDelay: `${i * 20}ms` }}
          >
            <span className="font-mono text-[10px] text-muted-foreground/70 shrink-0">
              {time}
            </span>
            <span className={`shrink-0 font-medium ${meta.cls}`}>{meta.icon}</span>
            <span className="font-medium truncate">{e.title}</span>
            {e.result && (
              <span className="text-muted-foreground truncate">
                — {e.result}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}
