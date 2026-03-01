/**
 * Requirement Analysis Artifact Detection and Parsing
 *
 * This module provides utilities for detecting and parsing requirement analysis
 * artifacts from AI messages in the chat interface.
 */

export interface Requirement {
  id: string
  description: string
  priority: string
  category: string
  acceptance_criteria: string[]
}

export interface UserStory {
  id: string
  role: string
  action: string
  benefit: string
  acceptance_criteria: string[]
}

export interface TechnicalSuggestion {
  area: string
  suggestion: string
  rationale: string
}

export interface Risk {
  description: string
  impact: string
  mitigation: string
}

export interface AnalysisData {
  title?: string
  summary?: string
  functional_requirements?: Requirement[]
  non_functional_requirements?: Requirement[]
  user_stories?: UserStory[]
  technical_suggestions?: TechnicalSuggestion[]
  risks?: Risk[]
  dependencies?: string[]
}

export interface RequirementAnalysisArtifact {
  type: "artifact"
  artifact_type: "requirement_analysis"
  data: {
    analysis_id: string
    document_id: string
    project_id: number
    analysis: AnalysisData
  }
}

/**
 * Detect if a message content contains a requirement analysis artifact
 */
export function detectRequirementAnalysis(content: string): boolean {
  if (!content || typeof content !== "string") return false

  const trimmed = content.trim()
  if (!trimmed.startsWith("{") || !trimmed.endsWith("}")) return false

  try {
    const obj = JSON.parse(trimmed) as RequirementAnalysisArtifact
    return (
      obj.type === "artifact" &&
      obj.artifact_type === "requirement_analysis" &&
      obj.data?.analysis_id !== undefined
    )
  } catch {
    return false
  }
}

/**
 * Parse requirement analysis artifact from message content
 * Returns null if parsing fails or content is not a valid artifact
 */
export function parseRequirementAnalysis(
  content: string
): RequirementAnalysisArtifact | null {
  if (!detectRequirementAnalysis(content)) return null

  try {
    return JSON.parse(content.trim()) as RequirementAnalysisArtifact
  } catch {
    return null
  }
}

/**
 * Check if message content is a structured artifact (any type)
 */
export function isArtifactMessage(content: string): boolean {
  if (!content || typeof content !== "string") return false

  const trimmed = content.trim()
  if (!trimmed.startsWith("{") || !trimmed.endsWith("}")) return false

  try {
    const obj = JSON.parse(trimmed)
    return obj.type === "artifact" && obj.artifact_type !== undefined
  } catch {
    return false
  }
}
