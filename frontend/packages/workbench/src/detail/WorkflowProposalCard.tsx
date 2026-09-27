import { Button } from "@evoloop/shared"
import { useQueryClient } from "@tanstack/react-query"
import { CalendarClock, CheckCircle2, Workflow } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"
import { TasksQueueService } from "@/client"

/**
 * 周期工作流提案卡（阶段九 UI 面）：
 * - 值守左栏「提案」tab 的 workflow 分组渲染 proposed/armed 工作流；
 * - confirm = 触发器上膛（armed，下一 cron 自动开跑）；取消 = cancel。
 * 阶段 DAG 以缩进链列表呈现（deps 只用于标层级，不画画布连线——
 * 画布容器节点是 D7，未实施）。
 */

export interface WorkflowProposal {
  id: string
  project_id: number
  title: string
  goal: string
  status: string
  trigger_spec: string | null
  next_run_at: string | null
  round_no: number
  stages: Array<{ key: string | null; title: string | null; deps: string[] }>
  created_at: string
  updated_at: string
}

function StageChain({ stages }: { stages: WorkflowProposal["stages"] }) {
  const depth = (key: string | null, seen = new Set<string>()): number => {
    if (!key || seen.has(key)) return 0
    seen.add(key)
    const stage = stages.find((s) => s.key === key)
    if (!stage || stage.deps.length === 0) return 0
    return 1 + Math.max(...stage.deps.map((d) => depth(d, seen)))
  }
  const sorted = [...stages].sort((a, b) => depth(a.key) - depth(b.key))
  return (
    <div className="mt-2 space-y-1 rounded-lg bg-muted/30 px-3 py-2">
      {sorted.map((s) => (
        <div
          key={s.key ?? s.title}
          className="flex items-center gap-1.5 text-[11.5px] text-muted-foreground"
          style={{ paddingLeft: `${depth(s.key) * 14}px` }}
        >
          <span className="h-1 w-1 rounded-full bg-muted-foreground/40" />
          <span className="truncate">{s.title ?? s.key}</span>
          {s.deps.length > 0 && (
            <span className="ml-auto shrink-0 font-mono text-[10px] opacity-60">
              ← {s.deps.join(" + ")}
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

export function WorkflowProposalCard({
  workflow,
  onChanged,
}: {
  workflow: WorkflowProposal
  onChanged: () => void | Promise<void>
}) {
  const qc = useQueryClient()
  const [busy, setBusy] = useState<"confirm" | "cancel" | null>(null)
  const isProposed = workflow.status === "proposed"

  async function handleConfirm() {
    if (busy) return
    setBusy("confirm")
    try {
      await TasksQueueService.confirmWorkflow({
        workflowId: workflow.id,
      })
      toast.success("工作流已上膛，将在下一个触发周期自动开跑")
      await qc.invalidateQueries({ queryKey: ["dutyWorkflows"] })
      await onChanged()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "工作流确认失败")
    } finally {
      setBusy(null)
    }
  }

  async function handleCancel() {
    if (busy) return
    setBusy("cancel")
    try {
      await TasksQueueService.editWorkflow({
        workflowId: workflow.id,
        requestBody: { cancel: true },
      })
      toast.success("工作流已取消")
      await qc.invalidateQueries({ queryKey: ["dutyWorkflows"] })
      await onChanged()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "工作流取消失败")
    } finally {
      setBusy(null)
    }
  }

  return (
    <div
      data-workflow-id={workflow.id}
      className="my-2 w-full overflow-hidden rounded-xl bg-background"
    >
      <div className="flex items-start gap-3 bg-violet-500/10 px-3.5 py-2.5">
        <CalendarClock className="mt-0.5 h-4 w-4 shrink-0 text-violet-500" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold tracking-wide text-muted-foreground">
              {isProposed ? "周期流水线提案" : "周期流水线"}
            </span>
            <span className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
              {workflow.status}
            </span>
            {workflow.trigger_spec && (
              <span className="ml-auto shrink-0 font-mono text-[10px] text-muted-foreground">
                ⏰ {workflow.trigger_spec}
              </span>
            )}
          </div>
          <h4 className="mt-1 truncate text-sm font-semibold">
            {workflow.title}
          </h4>
        </div>
      </div>

      <div className="space-y-2 px-3.5 py-3">
        {workflow.goal && (
          <div className="rounded-lg bg-muted/20 p-2.5 text-xs break-words text-muted-foreground">
            {workflow.goal}
          </div>
        )}
        {workflow.stages.length > 0 && <StageChain stages={workflow.stages} />}

        {isProposed ? (
          <div className="flex gap-2 pt-1">
            <Button
              size="sm"
              className="flex-1"
              disabled={busy !== null}
              onClick={handleConfirm}
            >
              <CheckCircle2 className="mr-1 h-4 w-4" />
              确认上膛（自动按周期开跑）
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={busy !== null}
              onClick={handleCancel}
            >
              <Workflow className="mr-1 h-4 w-4" />
              取消
            </Button>
          </div>
        ) : (
          <div className="flex items-center justify-between gap-2 rounded-lg bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            <span>
              {workflow.status === "armed" && "已上膛，等待触发周期"}
              {workflow.status === "running" &&
                `第 ${workflow.round_no} 轮执行中`}
              {workflow.status === "completed" &&
                `已收口（共 ${workflow.round_no} 轮）`}
              {workflow.status === "failed" && "有阶段失败，见任务列表"}
              {workflow.status === "cancelled" && "已取消"}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
