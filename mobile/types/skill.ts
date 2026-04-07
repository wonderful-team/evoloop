// 技能系统类型定义

/**
 * 技能类型
 */
export type SkillType = 'builtin' | 'custom' | 'mcp';

/**
 * 技能状态
 */
export type SkillStatus = 'active' | 'inactive' | 'error';

/**
 * 技能定义
 */
export interface Skill {
  id: string;
  name: string;
  description: string;
  type: SkillType;
  status: SkillStatus;
  version: string;
  author?: string;
  icon?: string;
  tags: string[];
  parameters?: SkillParameter[];
  created_at: string;
  updated_at: string;
}

/**
 * 技能参数
 */
export interface SkillParameter {
  name: string;
  type: 'string' | 'number' | 'boolean' | 'array' | 'object';
  description: string;
  required: boolean;
  default?: any;
  enum?: any[];
}

/**
 * 技能执行请求
 */
export interface SkillExecutionRequest {
  skill_id: string;
  parameters: Record<string, any>;
  context?: {
    conversation_id?: string;
    project_id?: number;
  };
}

/**
 * 技能执行响应
 */
export interface SkillExecutionResponse {
  execution_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  result?: any;
  error?: string;
  started_at: string;
  completed_at?: string;
}

/**
 * 技能执行状态
 */
export interface SkillExecutionStatus {
  execution_id: string;
  skill_id: string;
  skill_name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress?: number;
  result?: any;
  error?: string;
  started_at: string;
  updated_at: string;
  completed_at?: string;
}

/**
 * MCP 服务器
 */
export interface McpServer {
  id: string;
  name: string;
  description?: string;
  transport: 'stdio' | 'sse' | 'http';
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  status: 'connected' | 'disconnected' | 'error';
  tools: McpTool[];
  created_at: string;
  updated_at: string;
}

/**
 * MCP 工具
 */
export interface McpTool {
  name: string;
  description: string;
  parameters?: {
    type: string;
    properties: Record<string, any>;
    required?: string[];
  };
}

/**
 * 技能匹配结果
 */
export interface SkillMatch {
  skill_id: string;
  skill_name: string;
  confidence: number;
  matched_keywords: string[];
  description?: string;
}

/**
 * Agent 思考 - 技能匹配
 */
export interface SkillMatchThought {
  type: 'skill_match';
  thought_type: 'skill_match';
  title: string;
  content: {
    matched_skills: SkillMatch[];
    selected_skill?: string;
    reason?: string;
  };
  confidence: number;
  timestamp: number;
}
