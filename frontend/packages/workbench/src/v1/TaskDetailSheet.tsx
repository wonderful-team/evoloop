import { useTranslation } from "react-i18next"

import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import { Separator } from "@evoloop/shared/components/ui/separator"

import { TasksQueueApi, type QueueTask } from "@/lib/tasksQueueApi"

interface Props {
  task: QueueTask
  onChanged: () => void | Promise<void>
}

/** Detail drawer body: fields + self-check report + acceptance receipt. */
export function TaskDetailSheet({ task, onChanged }: Props) {
  const { t } = useTranslation()

  async function run(fn: () => Promise<unknown>) {
    await fn()
    await onChanged()
  }

  const sc = task.self_check as
    | {
        verdict?: string
        checks?: { name: string; pass: boolean; evidence?: string }[]
        deviations?: string[]
      }
    | null
  const ac = task.acceptance as
    | { by?: string; at?: string; verdict?: string; feedback?: string }
    | null

  return (
    <div className="space-y-4 mt-2">
      <div className="flex items-center gap-1.5 flex-wrap">
        <Badge variant="secondary">{task.status}</Badge>
        {task.type === "recurring" && (
          <Badge variant="outline">{t("dutyBoard.recurring")}</Badge>
        )}
        {task.risk_level && <Badge variant="outline">{task.risk_level}</Badge>}
        {task.category && (
          <Badge variant="outline">{task.category}</Badge>
        )}
        {task.priority && task.priority !== "medium" && (
          <Badge variant="outline">{task.priority}</Badge>
        )}
      </div>

      {task.description && (
        <div>
          <div className="text-xs font-medium text-muted-foreground mb-1">
            {t("dutyBoard.detail.instruction")}
          </div>
          <div className="rounded-md border bg-muted/40 p-2.5 text-sm whitespace-pre-wrap">
            {task.description}
          </div>
        </div>
      )}

      <Separator />

      <div>
        <div className="text-xs font-medium text-muted-foreground mb-1">
          {t("dutyBoard.detail.selfCheck")}
        </div>
        {sc ? (
          <div className="space-y-1.5 text-xs">
            <div>
              {t("dutyBoard.detail.verdict")}:{" "}
              <span
                className={
                  sc.verdict === "pass"
                    ? "text-green-600 font-medium"
                    : "text-orange-600 font-medium"
                }
              >
                {sc.verdict}
              </span>
            </div>
            {(sc.checks ?? []).map((c, i) => (
              <div key={i} className="flex items-start gap-1.5">
                <span>{c.pass ? "✓" : "✗"}</span>
                <span>
                  {c.name}
                  {c.evidence ? ` — ${c.evidence}` : ""}
                </span>
              </div>
            ))}
            {(sc.deviations ?? []).map((d, i) => (
              <div key={i} className="text-orange-600">
                ⚠ {d}
              </div>
            ))}
          </div>
        ) : (
          <div className="text-xs text-muted-foreground">—</div>
        )}
      </div>

      <Separator />

      <div>
        <div className="text-xs font-medium text-muted-foreground mb-1">
          {t("dutyBoard.detail.acceptance")}
        </div>
        {ac ? (
          <div className="text-xs space-y-0.5">
            <div>
              {ac.verdict} · {ac.by} ·{" "}
              {ac.at ? new Date(ac.at).toLocaleString() : ""}
            </div>
            {ac.feedback && (
              <div className="text-muted-foreground">{ac.feedback}</div>
            )}
          </div>
        ) : (
          <div className="text-xs text-muted-foreground">—</div>
        )}
      </div>

      {task.last_thread_id && (
        <>
          <Separator />
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            onClick={() => {
              /* wired to thread open in stage 4b */
            }}
          >
            {t("dutyBoard.action.openThread")}
          </Button>
        </>
      )}

      {task.status === "waiting_acceptance" && (
        <div className="flex gap-2">
          <Button
            className="flex-1"
            size="sm"
            onClick={() => run(() => TasksQueueApi.accept(task.id))}
          >
            {t("dutyBoard.action.accept")}
          </Button>
          <Button
            variant="outline"
            className="flex-1"
            size="sm"
            onClick={() => run(() => TasksQueueApi.reject(task.id, "rejected from detail"))}
          >
            {t("dutyBoard.action.reject")}
          </Button>
        </div>
      )}
    </div>
  )
}
