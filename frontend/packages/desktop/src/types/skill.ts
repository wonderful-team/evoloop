export interface LearnedSkill {
  id: number
  name: string
  description: string
  tools_used: string[]
  success_count: number
  trigger_patterns: string[]
  parameters: SkillParameter[]
  created_at: string
  updated_at: string
  is_active: boolean
  status?: string
  steps?: SkillStep[] | string
  failure_count?: number
  avg_duration?: string
  instructions?: string
  resource_path?: string
  validation_report?: {
    is_valid: boolean
    status: string
    errors: string[]
    warnings: string[]
    metadata?: any
  }
}

export interface SkillParameter {
  name: string
  type: string
  description: string
  default?: any
  required?: boolean
}

export interface VisualContext {
  screenshot_path?: string
  element_selector?: string
  element_text?: string
}

export interface SkillStep {
  id?: string
  action: string
  args: Record<string, any>
  condition?: string
  on_error?: string
  visual_context?: VisualContext
  trace_step_ref?: number
  children?: SkillStep[]
}
