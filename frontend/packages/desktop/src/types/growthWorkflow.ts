export type GrowthWorkflowStatus = "running" | "completed" | "failed"

export interface GrowthWorkflowTask {
  id: string
  stage: string
  role: string
  runtime: string
  status: string
  risk_level: string
  dependencies: string[]
  allowed_packages: string[]
  last_error?: string
  retry_count?: number
}

export interface GrowthWorkflow {
  id: string
  project_id: number
  title: string
  goal: string
  type: string
  status: GrowthWorkflowStatus
  inputs: Record<string, unknown>
  tasks: GrowthWorkflowTask[]
}

export interface GrowthWorkflowSummary {
  id: string
  project_id: number
  title: string
  goal: string
  type: string
  status: GrowthWorkflowStatus
  created_at: string
  updated_at: string
}

export interface GrowthWorkflowArtifact {
  id: string
  workflow_id: string
  task_id: string
  stage: string
  type: string
  status: string
  version: number
  summary: string
  data: Record<string, unknown>
  created_at: string
}

export interface CreateGrowthWorkflowRequest {
  project_id: number
  title: string
  goal: string
  inputs?: Record<string, unknown>
}
