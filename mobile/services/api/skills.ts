// 技能系统 API - 通过 Gateway 访问
// 链路: Mobile → Gateway (evoloop/backend) → 技能服务

import { api } from './client';
import { GATEWAY_API } from '@/constants/api';
import {
  Skill,
  SkillExecutionRequest,
  SkillExecutionResponse,
  SkillExecutionStatus,
  McpServer,
  SkillMatch,
} from '@/types/skill';

/**
 * 获取技能列表
 * GET /gateway/api/v1/skills
 */
export async function getSkills(type?: 'builtin' | 'custom' | 'mcp'): Promise<Skill[]> {
  const params = new URLSearchParams();
  if (type) params.append('type', type);
  
  const response = await api.get(`${GATEWAY_API.SKILLS}?${params.toString()}`);
  return response.data;
}

/**
 * 获取技能详情
 * GET /gateway/api/v1/skills/:id
 */
export async function getSkill(skillId: string): Promise<Skill> {
  const response = await api.get(`${GATEWAY_API.SKILLS}/${skillId}`);
  return response.data;
}

/**
 * 执行技能
 * POST /gateway/api/v1/skills/execute
 */
export async function executeSkill(
  request: SkillExecutionRequest
): Promise<SkillExecutionResponse> {
  const response = await api.post(GATEWAY_API.SKILL_EXECUTE, request);
  return response.data;
}

/**
 * 获取技能执行状态
 * GET /gateway/api/v1/skills/execution/:id
 */
export async function getSkillExecutionStatus(
  executionId: string
): Promise<SkillExecutionStatus> {
  const response = await api.get(GATEWAY_API.SKILL_EXECUTION(executionId));
  return response.data;
}

/**
 * 获取 MCP 服务器列表
 * GET /gateway/api/v1/mcp/servers
 */
export async function getMcpServers(): Promise<McpServer[]> {
  const response = await api.get(GATEWAY_API.MCP_SERVERS);
  return response.data;
}

/**
 * 获取 MCP 服务器详情
 * GET /gateway/api/v1/mcp/servers/:id
 */
export async function getMcpServer(serverId: string): Promise<McpServer> {
  const response = await api.get(`${GATEWAY_API.MCP_SERVERS}/${serverId}`);
  return response.data;
}

/**
 * 添加 MCP 服务器
 * POST /gateway/api/v1/mcp/servers
 */
export async function addMcpServer(
  data: Omit<McpServer, 'id' | 'created_at' | 'updated_at'>
): Promise<McpServer> {
  const response = await api.post(GATEWAY_API.MCP_SERVERS, data);
  return response.data;
}

/**
 * 更新 MCP 服务器
 * PUT /gateway/api/v1/mcp/servers/:id
 */
export async function updateMcpServer(
  serverId: string,
  data: Partial<McpServer>
): Promise<McpServer> {
  const response = await api.put(`${GATEWAY_API.MCP_SERVERS}/${serverId}`, data);
  return response.data;
}

/**
 * 删除 MCP 服务器
 * DELETE /gateway/api/v1/mcp/servers/:id
 */
export async function deleteMcpServer(serverId: string): Promise<void> {
  await api.delete(`${GATEWAY_API.MCP_SERVERS}/${serverId}`);
}

/**
 * 测试 MCP 连接
 * POST /gateway/api/v1/mcp/servers/:id/test
 */
export async function testMcpConnection(serverId: string): Promise<{
  success: boolean;
  message: string;
  tools_count?: number;
}> {
  const response = await api.post(`${GATEWAY_API.MCP_SERVERS}/${serverId}/test`);
  return response.data;
}

/**
 * 匹配技能
 * POST /gateway/api/v1/skills/match
 */
export async function matchSkills(
  query: string,
  context?: {
    conversation_id?: string;
    project_id?: number;
  }
): Promise<SkillMatch[]> {
  const response = await api.post(`${GATEWAY_API.SKILLS}/match`, {
    query,
    ...context,
  });
  return response.data;
}

/**
 * 获取推荐的技能
 * GET /gateway/api/v1/skills/recommended
 */
export async function getRecommendedSkills(
  conversationId?: string,
  limit = 5
): Promise<Skill[]> {
  const params = new URLSearchParams();
  if (conversationId) params.append('conversation_id', conversationId);
  params.append('limit', limit.toString());
  
  const response = await api.get(
    `${GATEWAY_API.SKILLS}/recommended?${params.toString()}`
  );
  return response.data;
}
