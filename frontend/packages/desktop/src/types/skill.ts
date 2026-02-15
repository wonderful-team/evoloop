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
  steps?: any[] | string
}

export interface SkillParameter {
  name: string
  type: string
  description: string
  default?: any
  required?: boolean
}
