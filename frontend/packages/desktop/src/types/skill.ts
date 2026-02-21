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
  failure_count?: number
  avg_duration?: string
  instructions?: string | null
  resource_path?: string
  validation_report?: {
    is_valid: boolean
    status: string
    errors: string[]
    warnings: string[]
    metadata?: any
  } | null
}


export interface SkillParameter {
  name: string
  type: string
  description: string
  default?: any
  required?: boolean
}


