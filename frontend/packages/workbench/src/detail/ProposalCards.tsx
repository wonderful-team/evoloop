import {useQueryClient} from "@tanstack/react-query"
import {TaskProposalCard} from "@evoloop/shared"
import {type QueueTask, TasksQueueApi} from "@/lib/tasksQueueApi"

export function ProposalCard({
  task,
  sourceTask,
  onChanged,
  onConfirmed,
}: {
  task: QueueTask
  sourceTask?: QueueTask | null
  onChanged: () => void | Promise<void>
  onConfirmed: () => void | Promise<void>
}) {
  async function handleConfirm() {
    await TasksQueueApi.confirm(task.id)
    await onChanged()
    await onConfirmed()
  }

  async function handleReject(feedback?: string) {
    if (!feedback?.trim()) return
    // 提案驳回 = 不采纳（cancel 语义）；acceptance reject 只接受
    // waiting_acceptance，对 proposed 会 409
    await TasksQueueApi.rejectProposed(task.id, feedback.trim())
    await onChanged()
  }

  return (
    <TaskProposalCard
      id={task.id}
      title={task.title}
      description={task.description}
      status={task.status}
      priority={task.priority}
      riskLevel={task.risk_level}
      category={task.category}
      sourceTaskTitle={sourceTask?.title}
      variant="default"
      requireFeedbackOnReject={true}
      allowScheduleEdit={false}
      onConfirm={handleConfirm}
      onReject={handleReject}
    />
  )
}

export function InlineProposal({
  proposal,
  onChanged,
}: {
  proposal: QueueTask
  onChanged: () => void | Promise<void>
}) {
  const qc = useQueryClient()

  async function handleConfirm() {
    await TasksQueueApi.confirm(proposal.id)
    await qc.invalidateQueries({ queryKey: ["dutyQueue"] })
    await qc.invalidateQueries({ queryKey: ["dutyDashboard"] })
    await onChanged()
  }

  async function handleReject(feedback?: string) {
    if (!feedback?.trim()) return
    await TasksQueueApi.rejectProposed(proposal.id, feedback.trim())
    await qc.invalidateQueries({ queryKey: ["dutyQueue"] })
    await qc.invalidateQueries({ queryKey: ["dutyDashboard"] })
    await onChanged()
  }

  return (
    <TaskProposalCard
      id={proposal.id}
      title={proposal.title}
      description={proposal.description}
      status={proposal.status}
      variant="inline"
      requireFeedbackOnReject={true}
      onConfirm={handleConfirm}
      onReject={handleReject}
    />
  )
}
