/* Tasks queue API client (autonomous duty board).
 * Hand-written until the OpenAPI codegen regenerates; mirrors sdk.gen patterns. */

import {OpenAPI} from "@/client"

const BASE = () => OpenAPI.BASE

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // 与生成客户端同源鉴权：OpenAPI.TOKEN（Bearer）+ Cookie 双通道，
  // 缺一会让 token-only 登录会话下的看板全量 401（被误渲染成空队列）
  const tokenRaw = OpenAPI.TOKEN
  const token =
    typeof tokenRaw === "function"
      ? await tokenRaw({ method: "GET" } as never)
      : tokenRaw
  const headers = new Headers(init?.headers)
  headers.set("Content-Type", "application/json")
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`)
  }
  const res = await fetch(`${BASE()}${path}`, {
    credentials: "include",
    ...init,
    headers,
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(
      (detail as { detail?: string } | null)?.detail ||
        `request failed: ${res.status}`,
    )
  }
  return res.json() as Promise<T>
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
  workflow_stage?: string | null
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

/** attempt 历史（task_runs 过程记录层，每任务最近 5 次） */
export interface TaskRunView {
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
}

export const TasksQueueApi = {
  list(
    status?: string,
    projectId?: number,
    rootOnly?: boolean,
    limit = 50,
    offset = 0,
  ): Promise<{
    items: QueueTask[]
    count: number
    has_more: boolean
    next_offset: number | null
  }> {
    const qs = new URLSearchParams()
    if (status) qs.set("status", status)
    if (projectId != null) qs.set("project_id", String(projectId))
    if (rootOnly != null) qs.set("root_only", String(rootOnly))
    qs.set("limit", String(limit))
    qs.set("offset", String(offset))
    return request(`/api/v1/tasks/queue?${qs.toString()}`)
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
  }): Promise<{ success: boolean; id: string; parent_id?: string | null; status: string }> {
    return request("/api/v1/tasks/queue", {
      method: "POST",
      body: JSON.stringify(body),
    })
  },
  update(
    taskId: string,
    body: Record<string, unknown>,
  ): Promise<{ success: boolean; id: string; status: string }> {
    return request(`/api/v1/tasks/queue/${taskId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    })
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
    return request(`/api/v1/tasks/queue/${taskId}/artifacts`)
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
    return request("/api/v1/tasks/queue/hitl-pending")
  },
  rerun(taskId: string): Promise<unknown> {
    return request(`/api/v1/tasks/queue/${taskId}/rerun`, { method: "POST" })
  },
  confirm(taskId: string): Promise<{ success: boolean; status: string }> {
    return request(`/api/v1/tasks/queue/${taskId}/confirm`, { method: "POST" })
  },
  accept(taskId: string): Promise<{ success: boolean; status: string }> {
    return request(`/api/v1/tasks/queue/${taskId}/accept`, { method: "POST" })
  },
  reject(taskId: string, feedback: string): Promise<{ success: boolean; status: string }> {
    return request(`/api/v1/tasks/queue/${taskId}/reject`, {
      method: "POST",
      body: JSON.stringify({ feedback }),
    })
  },
  /** 驳回提案（proposed）：语义是"不采纳、撤下提案"= cancel，
   *  与验收驳回（reject，仅 waiting_acceptance）是两个接口。 */
  rejectProposed(taskId: string, feedback: string): Promise<{ success: boolean; status: string }> {
    return request(`/api/v1/tasks/queue/${taskId}`, {
      method: "PUT",
      body: JSON.stringify({ cancel: true, description: feedback || undefined }),
    })
  },
  dashboard(projectId?: number): Promise<DashboardKpis> {
    const q = projectId != null ? `?project_id=${projectId}` : ""
    return request(`/api/v1/tasks/queue/dashboard${q}`)
  },
}
