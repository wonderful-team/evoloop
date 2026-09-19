/* Shared view types for the duty workbench panels. */

export interface Attachment {
  type: "image" | "video" | "file"
  label: string
  w: number
  h: number
  duration?: number
  hue: number
}

export interface PlanStep {
  id?: string
  title?: string
  status?: string
}

export interface ArtifactView {
  id?: string
  stage?: string
  type?: string
  summary: string
  data?: unknown
}
