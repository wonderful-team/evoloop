export type ProposalStatus =
  | "proposed"
  | "pending"
  | "in_progress"
  | "self_checked"
  | "waiting_acceptance"
  | "completed"
  | "cancelled"
  | "failed"
  | string

export interface ProposalScheduleParams {
  taskType: "once" | "recurring"
  scheduleMode?: "now" | "scheduled"
  dueAt?: string
  triggerSpec?: string
}

export interface TaskProposalCardProps {
  id?: string | null
  title?: string | null
  description?: string | null
  status?: ProposalStatus | null
  priority?: string | null
  riskLevel?: string | null
  category?: string | null
  source?: string | null
  sourceTaskTitle?: string | null
  error?: string | null

  variant?: "default" | "inline"
  allowScheduleEdit?: boolean
  initialTaskType?: "once" | "recurring"
  initialDueAt?: string | null
  initialTriggerSpec?: string | null

  // 驳回时是否要求输入原因（workbench 中为必填 feedback，chat 中为可选/取消）
  requireFeedbackOnReject?: boolean

  onConfirm?: (schedule?: ProposalScheduleParams) => Promise<void> | void
  onReject?: (feedback?: string) => Promise<void> | void
  onOpenDuty?: () => void
}
