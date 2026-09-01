// 技能系统 API
// 混合架构：查询类 (列表、详情) 走 Mobile → MC

import { api } from './client';
import {
  Skill,
  SkillExecutionStatus,
  McpServer,
  SkillMatch,
} from '@/types/skill';

/**
 * 获取技能列表 (MC 存储)
 * GET /member/api/skills
 */
export async function getSkills(type?: 'builtin' | 'custom' | 'mcp'): Promise<Skill[]> {
  const params = new URLSearchParams();
  if (type) params.append('type', type);
  
  const response = await api.get(`/member/api/skills?${params.toString()}`);
  return response.data;
}

/**
 * 获取技能详情 (MC 存储)
 * GET /member/api/skills/:id
 */
export async function getSkill(skillId: string): Promise<Skill> {
  const response = await api.get(`/member/api/skills/${skillId}`);
  return response.data;
}

/**
 * 获取技能执行状态 (MC 存储)
 * GET /member/api/skills/execution/:id
 */
export async function getSkillExecutionStatus(
  executionId: string
): Promise<SkillExecutionStatus> {
  const response = await api.get(`/member/api/skills/execution/${executionId}`);
  return response.data;
}

/**
 * 获取 MCP 服务器列表 (MC 存储)
 * GET /member/api/mcp/servers
 */
export async function getMcpServers(): Promise<McpServer[]> {
  const response = await api.get(`/member/mcp/servers`);
  return response.data;
}

/**
 * 获取 MCP 服务器详情 (MC 存储)
 * GET /member/api/mcp/servers/:id
 */
export async function getMcpServer(serverId: string): Promise<McpServer> {
  const response = await api.get(`/member/mcp/servers/${serverId}`);
  return response.data;
}

/**
 * 添加 MCP 服务器 (MC 存储)
 * POST /member/api/mcp/servers
 */
export async function addMcpServer(
  data: Omit<McpServer, 'id' | 'created_at' | 'updated_at'>
): Promise<McpServer> {
  const response = await api.post(`/member/mcp/servers`, data);
  return response.data;
}

/**
 * 更新 MCP 服务器 (MC 存储)
 * PUT /member/api/mcp/servers/:id
 */
export async function updateMcpServer(
  serverId: string,
  data: Partial<McpServer>
): Promise<McpServer> {
  const response = await api.put(`/member/mcp/servers/${serverId}`, data);
  return response.data;
}

/**
 * 删除 MCP 服务器 (MC 存储)
 * DELETE /member/api/mcp/servers/:id
 */
export async function deleteMcpServer(serverId: string): Promise<void> {
  await api.delete(`/member/mcp/servers/${serverId}`);
}

/**
 * 匹配技能 (MC 存储)
 * POST /member/api/skills/match
 */
export async function matchSkills(
  query: string,
  context?: {
    conversation_id?: string;
    project_id?: number;
  }
): Promise<SkillMatch[]> {
  const response = await api.post(`/member/api/skills/match`, {
    query,
    ...context,
  });
  return response.data;
}

/**
 * 获取推荐的技能 (MC 存储)
 * GET /member/api/skills/recommended
 */
export async function getRecommendedSkills(
  conversationId?: string,
  limit = 5
): Promise<Skill[]> {
  const params = new URLSearchParams();
  if (conversationId) params.append('conversation_id', conversationId);
  params.append('limit', limit.toString());
  
  const response = await api.get(
    `/member/api/skills/recommended?${params.toString()}`
  );
  return response.data;
}
