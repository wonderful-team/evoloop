// 技能系统 API
// 混合架构：
// - 查询类 (列表、详情): Mobile → MC
// - 执行类 (执行技能): Mobile → Gateway → Desktop

import { api } from './client';
import {
  Skill,
  SkillExecutionRequest,
  SkillExecutionResponse,
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
 * 执行技能
 */
export async function executeSkill(
  request: SkillExecutionRequest
): Promise<SkillExecutionResponse> {
  const envelope = {
    version: '2.0',
    type: 'command.relay',
    timestamp: Math.floor(Date.now() / 1000),
    source: { kind: 'mobile' },
    target: { kind: 'agent', device_key: request.deviceKey },
    body: {
      action: 'skill',
      content: {
        skill_id: request.skillId,
        params: request.params,
      },
    },
  };
  const response = await api.post(`/gateway/api/v1/message/send`, {
    target_device_key: request.deviceKey,
    envelope,
  });
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
 * 测试 MCP 连接（需提供 deviceKey，否则返回 400）
 */
export async function testMcpConnection(
  serverId: string,
  deviceKey?: string,
): Promise<{
  success: boolean;
  message: string;
  tools_count?: number;
}> {
  const envelope = {
    version: '2.0',
    type: 'command.relay',
    timestamp: Math.floor(Date.now() / 1000),
    source: { kind: 'mobile' },
    target: { kind: 'agent', device_key: deviceKey },
    body: {
      action: 'mcp_test',
      content: { server_id: serverId },
    },
  };
  const response = await api.post(`/gateway/api/v1/message/send`, {
    target_device_key: deviceKey || '',
    envelope,
  });
  return response.data;
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
