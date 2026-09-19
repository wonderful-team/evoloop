import { OpenAPI } from "@/client/core/OpenAPI"
import { request } from "@/client/core/request"
import type { CancelablePromise } from "@/client/core/CancelablePromise"
import type {
  CreateGrowthWorkflowRequest,
  GrowthWorkflow,
  GrowthWorkflowArtifact,
  GrowthWorkflowSummary,
} from "@/types/growthWorkflow"

interface WorkflowEnvelope {
  success: boolean
  workflow: GrowthWorkflow
}

interface ArtifactEnvelope {
  success: boolean
  count: number
  items: GrowthWorkflowArtifact[]
}

interface WorkflowSummaryEnvelope {
  success: boolean
  count: number
  items: GrowthWorkflowSummary[]
}

export class GrowthWorkflowService {
  public static createGrowthWorkflow(
    requestBody: CreateGrowthWorkflowRequest,
  ): CancelablePromise<WorkflowEnvelope> {
    return request(OpenAPI, {
      method: "POST",
      url: "/api/v1/tasks/workflows/growth",
      body: requestBody,
      mediaType: "application/json",
    })
  }

  public static getGrowthWorkflow(
    workflowId: string,
  ): CancelablePromise<WorkflowEnvelope> {
    return request(OpenAPI, {
      method: "GET",
      url: "/api/v1/tasks/workflows/{workflow_id}",
      path: { workflow_id: workflowId },
    })
  }

  public static listGrowthWorkflows(
    projectId: number,
  ): CancelablePromise<WorkflowSummaryEnvelope> {
    return request(OpenAPI, {
      method: "GET",
      url: "/api/v1/tasks/workflows",
      query: { project_id: projectId },
    })
  }

  public static listGrowthWorkflowArtifacts(
    workflowId: string,
  ): CancelablePromise<ArtifactEnvelope> {
    return request(OpenAPI, {
      method: "GET",
      url: "/api/v1/tasks/workflows/{workflow_id}/artifacts",
      path: { workflow_id: workflowId },
    })
  }
}
