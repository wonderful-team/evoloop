import { useNavigate } from "@tanstack/react-router"
import { CheckCircle2, ExternalLink, XCircle } from "lucide-react"

export interface DutyTaskMeta {
  task_id: string
  task_no?: number | null
  task_title?: string
  verdict: string
  feedback?: string
}

/**
 * 值守评审结论卡（Chat→Canvas 互链）：
 * 评审回复消息 meta_data.duty_task 由后端 review 链路落库；
 * 点击跳转值守画布并 flyToCard 定位（sessionStorage 一次性交接）。
 */
export function TaskStateChip({ meta }: { meta: DutyTaskMeta }) {
  const navigate = useNavigate()
  const accepted = meta.verdict === "accepted"
  const label = meta.task_no ? `#T-${meta.task_no}` : meta.task_id.slice(0, 8)

  function openInCanvas() {
    try {
      sessionStorage.setItem("duty:focus-task", meta.task_id)
    } catch {
      // 隐私模式等场景：退化为仅跳转不做定位
    }
    navigate({ to: "/duty-autonomous" })
  }

  return (
    <button
      type="button"
      onClick={openInCanvas}
      className={`mt-1.5 inline-flex max-w-full items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition-colors hover:border-primary/50 hover:bg-primary/5 ${
        accepted
          ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400"
          : "border-red-500/30 bg-red-500/5 text-red-600 dark:text-red-400"
      }`}
      title={meta.feedback || meta.task_title || ""}
    >
      {accepted ? (
        <CheckCircle2 className="h-3 w-3 shrink-0" />
      ) : (
        <XCircle className="h-3 w-3 shrink-0" />
      )}
      <span className="truncate">
        {label}
        {meta.task_title ? ` · ${meta.task_title}` : ""}
        {" · "}
        {accepted ? "评审通过" : "评审未通过"}
      </span>
      <ExternalLink className="h-3 w-3 shrink-0 opacity-60" />
    </button>
  )
}
