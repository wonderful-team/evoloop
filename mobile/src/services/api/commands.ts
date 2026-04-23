// 指令下达 API - 通过 Gateway 向 Desktop 下达指令
// 链路: Mobile → Gateway → Desktop (WebSocket)

import { api } from './client';
import { GATEWAY_API } from '@/constants/api';

// ========== 类型定义 ==========

/** 指令类型 */
export type CommandType = 
  | 'chat'           // 发送消息
  | 'stop'           // 停止生成
  | 'rewind'         // 回退
  | 'retry'          // 重试
  | 'skill'          // 执行 Skill
  | 'mcp'            // 调用 MCP
  | 'hitl_confirm'   // HITL 确认
  | 'hitl_choice'    // HITL 选择
  | 'hitl_text'      // HITL 文本
  | 'project_switch' // 切换项目
  | 'device_command' // 设备指令
  | string;          // 扩展类型

/** 通用指令请求 */
export interface ExecuteCommandRequest {
  command_type: CommandType;
  thread_id?: string;
  device_key?: string;  // 目标设备 Key，指定哪台 Desktop 执行
  payload: Record<string, any>;
}

/** 通用指令响应 */
export interface ExecuteCommandResponse {
  code: number;
  message: string;
  data?: any;
  request_id?: string;
}

/** 附件 */
export interface Attachment {
  type: 'image' | 'file' | 'audio';
  url: string;
  name: string;
  mime_type: string;
}

/** 聊天消息负载 */
export interface ChatPayload {
  content: string;
  attachments?: Attachment[];
  model?: string;
  options?: Record<string, any>;
}

/** Rewind 负载 */
export interface RewindPayload {
  message_id?: string;
  revert_files?: boolean;
}

/** Retry 负载 */
export interface RetryPayload {
  message_id?: string;
  revert_files?: boolean;
}

/** HITL 响应负载 */
export interface HITLPayload {
  request_id: string;
  response: string;
  data?: Record<string, any>;
}

/** Skill 执行负载 */
export interface SkillPayload {
  skill_id: string;
  params?: Record<string, any>;
}

/** MCP 调用负载 */
export interface MCPPayload {
  server_id: string;
  tool_name: string;
  args?: Record<string, any>;
}

/** 项目切换负载 */
export interface ProjectSwitchPayload {
  project_id: number;
}

/** 设备指令负载 */
export interface DeviceCommandPayload {
  device_key: string;
  command: string;
  params?: Record<string, any>;
}

// ========== 核心指令 API ==========

/**
 * 通用指令执行 - 核心接口
 * 所有指令都可以通过此接口下发
 * 
 * @param request 指令请求
 * @returns 指令响应
 */
export async function executeCommand(
  request: ExecuteCommandRequest
): Promise<ExecuteCommandResponse> {
  return api.post(GATEWAY_API.COMMAND_EXECUTE, request);
}

/**
 * 发送聊天消息 - 触发 Agent 执行链
 */
export async function sendChatMessage(
  threadId: string,
  payload: ChatPayload,
  deviceKey?: string
): Promise<ExecuteCommandResponse> {
  return executeCommand({
    command_type: 'chat',
    thread_id: threadId,
    device_key: deviceKey,
    payload: payload as Record<string, any>,
  });
}

/**
 * 停止 Agent 执行
 */
export async function stopExecution(
  threadId: string
): Promise<ExecuteCommandResponse> {
  return api.post(GATEWAY_API.CONVERSATION_STOP(threadId), {});
}

/**
 * Rewind 回退到指定消息
 */
export async function rewindThread(
  threadId: string,
  payload: RewindPayload = {}
): Promise<ExecuteCommandResponse> {
  return api.post(GATEWAY_API.CONVERSATION_REWIND(threadId), payload);
}

/**
 * Retry 重试执行
 */
export async function retryThread(
  threadId: string,
  payload: RetryPayload = {}
): Promise<ExecuteCommandResponse> {
  return api.post(GATEWAY_API.CONVERSATION_RETRY(threadId), payload);
}

// ========== HITL 交互 API ==========

/**
 * HITL 确认响应
 */
export async function hitlConfirm(
  payload: HITLPayload
): Promise<ExecuteCommandResponse> {
  return api.post(GATEWAY_API.HITL_CONFIRM, payload);
}

/**
 * HITL 选择响应
 */
export async function hitlChoice(
  payload: HITLPayload
): Promise<ExecuteCommandResponse> {
  return api.post(GATEWAY_API.HITL_CHOICE, payload);
}

/**
 * HITL 文本响应
 */
export async function hitlText(
  payload: HITLPayload
): Promise<ExecuteCommandResponse> {
  return api.post(GATEWAY_API.HITL_TEXT, payload);
}

// ========== 工具执行 API ==========

/**
 * 执行 Skill
 */
export async function executeSkill(
  payload: SkillPayload & { device_key?: string }
): Promise<ExecuteCommandResponse> {
  return executeCommand({
    command_type: 'skill',
    device_key: payload.device_key,
    payload: {
      skill_id: payload.skill_id,
      params: payload.params,
    },
  });
}

/**
 * 调用 MCP Tool
 */
export async function invokeMCPTool(
  payload: MCPPayload & { device_key?: string }
): Promise<ExecuteCommandResponse> {
  return executeCommand({
    command_type: 'mcp',
    device_key: payload.device_key,
    payload: {
      server_id: payload.server_id,
      tool_name: payload.tool_name,
      args: payload.args,
    },
  });
}

// ========== 项目/设备控制 API ==========

/**
 * 切换项目
 */
export async function switchProject(
  payload: ProjectSwitchPayload & { device_key?: string }
): Promise<ExecuteCommandResponse> {
  return executeCommand({
    command_type: 'project_switch',
    device_key: payload.device_key,
    payload: {
      project_id: payload.project_id,
    },
  });
}

/**
 * 发送设备指令
 */
export async function sendDeviceCommand(
  deviceKey: string,
  command: string,
  params?: Record<string, any>
): Promise<ExecuteCommandResponse> {
  return executeCommand({
    command_type: 'device_command',
    device_key: deviceKey,
    payload: {
      command,
      params,
    },
  });
}

// ========== 快捷指令封装 ==========

/**
 * 快捷指令 - 分析代码
 */
export async function quickAnalyzeCode(
  threadId: string,
  filePath: string
): Promise<ExecuteCommandResponse> {
  return sendChatMessage(threadId, {
    content: `分析文件: ${filePath}`,
  });
}

/**
 * 快捷指令 - 生成测试
 */
export async function quickGenerateTests(
  threadId: string,
  filePath: string
): Promise<ExecuteCommandResponse> {
  return sendChatMessage(threadId, {
    content: `为 ${filePath} 生成单元测试`,
  });
}

/**
 * 快捷指令 - 修复 Bug
 */
export async function quickFixBug(
  threadId: string,
  description: string
): Promise<ExecuteCommandResponse> {
  return sendChatMessage(threadId, {
    content: `修复问题: ${description}`,
  });
}

/**
 * 快捷指令 - 提交代码
 */
export async function quickCommit(
  threadId: string,
  message?: string
): Promise<ExecuteCommandResponse> {
  const commitMsg = message || '自动提交';
  return sendChatMessage(threadId, {
    content: `提交代码: ${commitMsg}`,
  });
}

// ========== 批量指令 ==========

/**
 * 批量执行指令
 * 按顺序执行多个指令，任一失败则停止
 */
export async function executeBatchCommands(
  commands: ExecuteCommandRequest[]
): Promise<ExecuteCommandResponse[]> {
  const results: ExecuteCommandResponse[] = [];
  
  for (const command of commands) {
    try {
      const result = await executeCommand(command);
      results.push(result);
      
      // 如果失败，停止后续执行
      if (result.code !== 0) {
        break;
      }
    } catch (error) {
      results.push({
        code: -1,
        message: error instanceof Error ? error.message : 'Unknown error',
      });
      break;
    }
  }
  
  return results;
}

// ========== 指令状态追踪 ==========

/** 指令状态 */
export type CommandStatus = 
  | 'pending'      // 等待执行
  | 'executing'    // 执行中
  | 'completed'    // 已完成
  | 'failed'       // 执行失败
  | 'cancelled';   // 已取消

/** 指令执行器 - 带状态追踪 */
export class CommandExecutor {
  private status: CommandStatus = 'pending';
  private requestId: string | null = null;
  private abortController: AbortController | null = null;

  /**
   * 执行指令
   */
  async execute(request: ExecuteCommandRequest): Promise<ExecuteCommandResponse> {
    this.status = 'executing';
    this.abortController = new AbortController();

    try {
      const response = await executeCommand(request);
      
      this.requestId = response.request_id || null;
      this.status = response.code === 0 ? 'completed' : 'failed';
      
      return response;
    } catch (error) {
      this.status = 'failed';
      throw error;
    }
  }

  /**
   * 取消执行
   */
  cancel(): void {
    if (this.abortController) {
      this.abortController.abort();
      this.status = 'cancelled';
    }
  }

  /**
   * 获取当前状态
   */
  getStatus(): CommandStatus {
    return this.status;
  }

  /**
   * 获取请求 ID
   */
  getRequestId(): string | null {
    return this.requestId;
  }
}

// ========== 导出 ==========

export const commandApi = {
  // 核心指令
  execute: executeCommand,
  sendChatMessage,
  stopExecution,
  rewindThread,
  retryThread,
  
  // HITL
  hitlConfirm,
  hitlChoice,
  hitlText,
  
  // 工具执行
  executeSkill,
  invokeMCPTool,
  
  // 项目/设备
  switchProject,
  sendDeviceCommand,
  
  // 快捷指令
  quick: {
    analyzeCode: quickAnalyzeCode,
    generateTests: quickGenerateTests,
    fixBug: quickFixBug,
    commit: quickCommit,
  },
  
  // 批量执行
  executeBatch: executeBatchCommands,
  
  // 执行器
  createExecutor: () => new CommandExecutor(),
};

export default commandApi;
