/* Tasks queue API facade (autonomous duty board).
 *
 * 单一来源收敛（2026-09-25）：HTTP 路径/鉴权/参数名全部由生成的
 * `TasksQueueService`（@/client，sdk.gen.ts）承担；本文件只剩三件事：
 * 1. 站内通用强类型（QueueTask/TaskRunView/QueueArtifact/DashboardKpis）——
 *    生成端 response 类型是宽松 dict，消费方零感知；
 * 2. 语义化方法名（reject/rejectProposed 的 cancel 语义分流等）；
 * 3. 错误透传：ApiError 的 body.detail 提升为 Error.message（与旧手写
 *    client 的 UX 契约一致，toast 能看到后端原因而非泛化状态码）。
 * 新增端点一律先 generate-client 再在此补门面方法，禁止再手写 fetch/路径。
 */

import type { TasksQueueEditTaskData } from "@/client"
import { TasksQueueService } from "@/client"
import { ApiError } from "@/client/core/ApiError"

async function unwrap<T>(call: Promise<T>): Promise<T> {
  try {
    return await call
  } catch (err) {
    if (err instanceof ApiError) {
      const body = err.body as { detail?: string } | null
      throw new Error(body?.detail || err.statusText || String(err.status))
    }
    throw err
  }
}

export interface QueueTask {
  id: string
  title: string | null
  description: string | null
  type: string | null
  status: string
  category: string | null
  priority: string | null
  risk_level: string | null
  source: string
  provenance: Record<string, unknown> | null
  self_check: Record<string, unknown> | null
  acceptance: Record<string, unknown> | null
  acceptance_criteria?: string[] | null
  task_no?: number | null
  review_pending?: boolean
  review_count?: number
  escalated?: boolean
  last_error?: string | null
  last_result?: string | null
  origin_thread_id?: string | null
  due_at: string | null
  last_thread_id: string | null
  parent_id?: string | null
  subtasks_count?: number
  subtasks_completed?: number
  project_id?: number | null
  dependencies?: string[] | null
  trigger_spec?: string | null
  elapsed_sec?: number | null
  created_at?: string | null
  updated_at?: string | null
  workflow_id?: string | null
  workflow_round?: number | null
  run?: {
    thread_id: string
    status: string
    llm_calls: number
    input_tokens: number
    output_tokens: number
    tool_errors: number
  } | null
  runs?: TaskRunView[]
  artifacts?: QueueArtifact[]
}

/** attempt 历史（task_runs 过程记录层，每任务最近 5 次；仅本文件 QueueTask 消费） */
interface TaskRunView {
  id: string
  thread_id: string | null
  attempt: number
  status: string
  started_at: string | null
  finished_at: string | null
  error_code: string | null
  error_message: string | null
  result_summary: string | null
}

export interface QueueArtifact {
  id: string
  workflow_id: string
  task_id: string
  stage: string
  type: string
  status: string
  version: number
  summary: string
  data: Record<string, unknown> | null
  created_at: string
}

export interface DashboardKpis {
  counts: Record<string, number>
  duty_state: "busy" | "idle" | "error"
  duty_enabled?: boolean
  tokens: {
    today: { input: number; output: number; llm_calls: number }
    week: { input: number; output: number; llm_calls: number }
  }
  today_window: { since: string | null; until: string | null }
  daily: {
    date: string
    input_tokens: number
    output_tokens: number
    completed: number
  }[]
  recent_events: {
    at: string | null
    kind: string
    title: string | null
    status: string
    task_id: string
    result: string
  }[]
  current_run: {
    thread_id: string
    goal: string
    started_at: string | null
    input_tokens: number
    output_tokens: number
  } | null
  workflows?: Array<{
    id: string
    title: string
    status: string
    round_no: number
    trigger_spec?: string | null
    tasks_total: number
    tasks_completed: number
  }>
}

export const TasksQueueApi = {
  list(
    status?: string,
    projectId?: number,
    rootOnly?: boolean,
    limit = 50,
    offset = 0,
    order?: "queue" | "recent",
  ): Promise<{
    items: QueueTask[]
    count: number
    has_more: boolean
    next_offset: number | null
  }> {
    return unwrap(
      TasksQueueService.listQueue({
        status,
        projectId,
        rootOnly,
        limit,
        offset,
        order,
      }),
    ) as never
  },
  create(body: {
    title: string
    description?: string
    type?: "once" | "recurring"
    category?: string
    priority?: string
    risk_level?: string
    trigger_spec?: string
    due_at?: string
    project_id: number
    parent_id?: string | null
    dependencies?: string[]
  }): Promise<{
    success: boolean
    id: string
    parent_id?: string | null
    status: string
  }> {
    return unwrap(TasksQueueService.createTask({ requestBody: body as any })) as never
  },
  update(
    taskId: string,
    body: Record<string, unknown>,
  ): Promise<{ success: boolean; id: string; status: string }> {
    return unwrap(
      TasksQueueService.editTask({
        taskId,
        requestBody: body as TasksQueueEditTaskData["requestBody"],
      }),
    ) as never
  },
  artifacts(taskId: string): Promise<{
    success: boolean
    items: {
      id: string
      stage: string
      artifact_type: string
      status: string
      version: number
      summary: string | null
      created_at: string | null
    }[]
  }> {
    return unwrap(TasksQueueService.listTaskArtifacts({ taskId })) as never
  },
  hitlPending(): Promise<{
    success: boolean
    count: number
    items: {
      request_id: string
      thread_id: string
      type: string
      description: string
      context: string | null
      options: string[]
      created_at: string | null
      task_id: string | null
      task_title: string | null
    }[]
  }> {
    return unwrap(TasksQueueService.hitlPendingTasks()) as never
  },
  rerun(taskId: string): Promise<unknown> {
    return unwrap(TasksQueueService.rerunFailedTask({ taskId })) as never
  },
  confirm(taskId: string): Promise<{ success: boolean; status: string }> {
    return unwrap(TasksQueueService.confirmProposal({ taskId })) as never
  },
  accept(taskId: string): Promise<{ success: boolean; status: string }> {
    return unwrap(TasksQueueService.acceptTask({ taskId })) as never
  },
  reject(
    taskId: string,
    feedback: string,
  ): Promise<{ success: boolean; status: string }> {
    return unwrap(
      TasksQueueService.rejectTask({
        taskId,
        requestBody: { feedback },
      }),
    ) as never
  },
  /** 驳回提案（proposed）：语义是"不采纳、撤下提案"= cancel，
   *  与验收驳回（reject，仅 waiting_acceptance）是两个接口。 */
  rejectProposed(
    taskId: string,
    feedback: string,
  ): Promise<{ success: boolean; status: string }> {
    return unwrap(
      TasksQueueService.editTask({
        taskId,
        requestBody: { cancel: true, description: feedback || undefined },
      }),
    ) as never
  },
  dashboard(projectId?: number): Promise<DashboardKpis> {
    return unwrap(TasksQueueService.queueDashboard({ projectId })) as never
  },
}
