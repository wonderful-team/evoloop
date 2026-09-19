/* Tasks queue API client (autonomous duty board).
 * Hand-written until the OpenAPI codegen regenerates; mirrors sdk.gen patterns. */

import { OpenAPI } from "@/client"

const BASE = () => OpenAPI.BASE

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE()}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...init,
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
  due_at: string | null
  last_thread_id: string | null
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
  artifacts?: QueueArtifact[]
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
  ): Promise<{ items: QueueTask[]; count: number }> {
    const qs = new URLSearchParams()
    if (status) qs.set("status", status)
    if (projectId != null) qs.set("project_id", String(projectId))
    const q = qs.toString() ? `?${qs.toString()}` : ""
    return request(`/api/v1/tasks/queue${q}`)
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
  }): Promise<{ success: boolean; id: string; status: string }> {
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
  dashboard(projectId?: number): Promise<DashboardKpis> {
    const q = projectId != null ? `?project_id=${projectId}` : ""
    return request(`/api/v1/tasks/queue/dashboard${q}`)
  },
}
