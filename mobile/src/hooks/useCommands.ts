// 指令下达 Hook - 封装向 Gateway 下达指令的逻辑
// 提供简洁的指令调用方式和状态管理

import { useState, useCallback, useRef } from 'react';
import { commandApi } from '@/services/api';
import type {
  CommandType,
  ExecuteCommandRequest,
  ExecuteCommandResponse,
  ChatPayload,
  RewindPayload,
  RetryPayload,
  HITLPayload,
  SkillPayload,
  MCPPayload,
  CommandStatus,
  CommandExecutor,
} from '@/services/api/commands';

/** Hook 返回类型 */
interface UseCommandsReturn {
  // 状态
  isLoading: boolean;
  error: string | null;
  status: CommandStatus;
  requestId: string | null;
  
  // 核心指令方法
  execute: (type: CommandType, payload: Record<string, any>, threadId?: string, deviceKey?: string) => Promise<ExecuteCommandResponse>;
  sendMessage: (threadId: string, content: string, options?: Partial<ChatPayload> & { deviceKey?: string }) => Promise<ExecuteCommandResponse>;
  stop: (threadId: string, deviceKey?: string) => Promise<ExecuteCommandResponse>;
  rewind: (threadId: string, payload?: RewindPayload, deviceKey?: string) => Promise<ExecuteCommandResponse>;
  retry: (threadId: string, payload?: RetryPayload, deviceKey?: string) => Promise<ExecuteCommandResponse>;
  
  // HITL 方法
  hitlConfirm: (requestId: string, response: string, data?: Record<string, any>) => Promise<ExecuteCommandResponse>;
  hitlChoice: (requestId: string, choiceId: string, data?: Record<string, any>) => Promise<ExecuteCommandResponse>;
  hitlText: (requestId: string, text: string) => Promise<ExecuteCommandResponse>;
  
  // 工具执行
  executeSkill: (skillId: string, params?: Record<string, any>) => Promise<ExecuteCommandResponse>;
  invokeMCP: (serverId: string, toolName: string, args?: Record<string, any>) => Promise<ExecuteCommandResponse>;
  
  // 项目/设备控制
  switchProject: (projectId: number) => Promise<ExecuteCommandResponse>;
  sendDeviceCommand: (deviceKey: string, command: string, params?: Record<string, any>) => Promise<ExecuteCommandResponse>;
  
  // 快捷指令
  quick: {
    analyzeCode: (threadId: string, filePath: string) => Promise<ExecuteCommandResponse>;
    generateTests: (threadId: string, filePath: string) => Promise<ExecuteCommandResponse>;
    fixBug: (threadId: string, description: string) => Promise<ExecuteCommandResponse>;
    commit: (threadId: string, message?: string) => Promise<ExecuteCommandResponse>;
  };
  
  // 控制
  cancel: () => void;
  reset: () => void;
}

/**
 * 指令下达 Hook
 * 
 * @example
 * ```typescript
 * const { sendMessage, stop, isLoading, status } = useCommands();
 * 
 * // 发送消息
 * await sendMessage('thread_xxx', '分析一下代码');
 * 
 * // 停止生成
 * await stop('thread_xxx');
 * ```
 */
export function useCommands(): UseCommandsReturn {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<CommandStatus>('pending');
  const [requestId, setRequestId] = useState<string | null>(null);
  
  // 使用 ref 存储 executor，确保在组件重新渲染时保持一致
  const executorRef = useRef<CommandExecutor | null>(null);
  
  // 获取或创建 executor
  const getExecutor = useCallback(() => {
    if (!executorRef.current) {
      executorRef.current = commandApi.createExecutor();
    }
    return executorRef.current;
  }, []);

  /**
   * 重置状态
   */
  const reset = useCallback(() => {
    setIsLoading(false);
    setError(null);
    setStatus('pending');
    setRequestId(null);
    executorRef.current = null;
  }, []);

  /**
   * 取消执行
   */
  const cancel = useCallback(() => {
    getExecutor().cancel();
    setStatus('cancelled');
    setIsLoading(false);
  }, [getExecutor]);

  /**
   * 执行通用指令
   */
  const execute = useCallback(async (
    type: CommandType,
    payload: Record<string, any>,
    threadId?: string,
    deviceKey?: string
  ): Promise<ExecuteCommandResponse> => {
    setIsLoading(true);
    setError(null);
    setStatus('executing');
    
    try {
      const request: ExecuteCommandRequest = {
        command_type: type,
        thread_id: threadId,
        device_key: deviceKey,
        payload,
      };
      
      const response = await commandApi.execute(request);
      
      setRequestId(response.request_id || null);
      setStatus(response.code === 0 ? 'completed' : 'failed');
      
      if (response.code !== 0) {
        setError(response.message);
      }
      
      return response;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      setStatus('failed');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * 发送聊天消息
   * @param deviceKey 指定目标设备（可选，默认使用当前选中的设备）
   */
  const sendMessage = useCallback(async (
    threadId: string,
    content: string,
    options?: Partial<ChatPayload> & { deviceKey?: string }
  ): Promise<ExecuteCommandResponse> => {
    setIsLoading(true);
    setError(null);
    setStatus('executing');
    
    try {
      const { deviceKey, ...chatOptions } = options || {};
      const payload: ChatPayload = {
        content,
        ...chatOptions,
      };
      
      const response = await commandApi.sendChatMessage(threadId, payload, deviceKey);
      
      setRequestId(response.request_id || null);
      setStatus(response.code === 0 ? 'completed' : 'failed');
      
      if (response.code !== 0) {
        setError(response.message);
      }
      
      return response;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      setStatus('failed');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * 停止执行
   */
  const stop = useCallback(async (
    threadId: string,
    deviceKey?: string
  ): Promise<ExecuteCommandResponse> => {
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await commandApi.stopExecution(threadId, deviceKey);
      
      setStatus(response.code === 0 ? 'completed' : 'failed');
      
      if (response.code !== 0) {
        setError(response.message);
      }
      
      return response;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      setStatus('failed');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * Rewind 回退
   */
  const rewind = useCallback(async (
    threadId: string,
    payload?: RewindPayload,
    deviceKey?: string
  ): Promise<ExecuteCommandResponse> => {
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await commandApi.rewindThread(threadId, payload, deviceKey);
      
      setStatus(response.code === 0 ? 'completed' : 'failed');
      
      if (response.code !== 0) {
        setError(response.message);
      }
      
      return response;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      setStatus('failed');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * Retry 重试
   */
  const retry = useCallback(async (
    threadId: string,
    payload?: RetryPayload,
    deviceKey?: string
  ): Promise<ExecuteCommandResponse> => {
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await commandApi.retryThread(threadId, payload, deviceKey);
      
      setStatus(response.code === 0 ? 'completed' : 'failed');
      
      if (response.code !== 0) {
        setError(response.message);
      }
      
      return response;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      setStatus('failed');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * HITL 确认
   */
  const hitlConfirm = useCallback(async (
    requestId: string,
    response: string,
    data?: Record<string, any>
  ): Promise<ExecuteCommandResponse> => {
    setIsLoading(true);
    setError(null);
    
    try {
      const payload: HITLPayload = {
        request_id: requestId,
        response,
        data,
      };
      
      const result = await commandApi.hitlConfirm(payload);
      
      setStatus(result.code === 0 ? 'completed' : 'failed');
      
      if (result.code !== 0) {
        setError(result.message);
      }
      
      return result;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      setStatus('failed');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * HITL 选择
   */
  const hitlChoice = useCallback(async (
    requestId: string,
    choiceId: string,
    data?: Record<string, any>
  ): Promise<ExecuteCommandResponse> => {
    setIsLoading(true);
    setError(null);
    
    try {
      const payload: HITLPayload = {
        request_id: requestId,
        response: choiceId,
        data,
      };
      
      const result = await commandApi.hitlChoice(payload);
      
      setStatus(result.code === 0 ? 'completed' : 'failed');
      
      if (result.code !== 0) {
        setError(result.message);
      }
      
      return result;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      setStatus('failed');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * HITL 文本
   */
  const hitlText = useCallback(async (
    requestId: string,
    text: string
  ): Promise<ExecuteCommandResponse> => {
    setIsLoading(true);
    setError(null);
    
    try {
      const payload: HITLPayload = {
        request_id: requestId,
        response: text,
      };
      
      const result = await commandApi.hitlText(payload);
      
      setStatus(result.code === 0 ? 'completed' : 'failed');
      
      if (result.code !== 0) {
        setError(result.message);
      }
      
      return result;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      setStatus('failed');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * 执行 Skill
   */
  const executeSkill = useCallback(async (
    skillId: string,
    params?: Record<string, any>
  ): Promise<ExecuteCommandResponse> => {
    setIsLoading(true);
    setError(null);
    
    try {
      const payload: SkillPayload = {
        skill_id: skillId,
        params,
      };
      
      const response = await commandApi.executeSkill(payload);
      
      setStatus(response.code === 0 ? 'completed' : 'failed');
      
      if (response.code !== 0) {
        setError(response.message);
      }
      
      return response;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      setStatus('failed');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * 调用 MCP
   */
  const invokeMCP = useCallback(async (
    serverId: string,
    toolName: string,
    args?: Record<string, any>
  ): Promise<ExecuteCommandResponse> => {
    setIsLoading(true);
    setError(null);
    
    try {
      const payload: MCPPayload = {
        server_id: serverId,
        tool_name: toolName,
        args,
      };
      
      const response = await commandApi.invokeMCPTool(payload);
      
      setStatus(response.code === 0 ? 'completed' : 'failed');
      
      if (response.code !== 0) {
        setError(response.message);
      }
      
      return response;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      setStatus('failed');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * 切换项目
   */
  const switchProject = useCallback(async (
    projectId: number
  ): Promise<ExecuteCommandResponse> => {
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await commandApi.switchProject({ project_id: projectId });
      
      setStatus(response.code === 0 ? 'completed' : 'failed');
      
      if (response.code !== 0) {
        setError(response.message);
      }
      
      return response;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      setStatus('failed');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * 发送设备指令
   */
  const sendDeviceCommand = useCallback(async (
    deviceKey: string,
    command: string,
    params?: Record<string, any>
  ): Promise<ExecuteCommandResponse> => {
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await commandApi.sendDeviceCommand(deviceKey, command, params);
      
      setStatus(response.code === 0 ? 'completed' : 'failed');
      
      if (response.code !== 0) {
        setError(response.message);
      }
      
      return response;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      setStatus('failed');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * 快捷指令对象
   */
  const quick = {
    analyzeCode: useCallback((threadId: string, filePath: string) => {
      return sendMessage(threadId, `分析文件: ${filePath}`);
    }, [sendMessage]),
    
    generateTests: useCallback((threadId: string, filePath: string) => {
      return sendMessage(threadId, `为 ${filePath} 生成单元测试`);
    }, [sendMessage]),
    
    fixBug: useCallback((threadId: string, description: string) => {
      return sendMessage(threadId, `修复问题: ${description}`);
    }, [sendMessage]),
    
    commit: useCallback((threadId: string, message?: string) => {
      const commitMsg = message || '自动提交';
      return sendMessage(threadId, `提交代码: ${commitMsg}`);
    }, [sendMessage]),
  };

  return {
    // 状态
    isLoading,
    error,
    status,
    requestId,
    
    // 核心方法
    execute,
    sendMessage,
    stop,
    rewind,
    retry,
    
    // HITL
    hitlConfirm,
    hitlChoice,
    hitlText,
    
    // 工具执行
    executeSkill,
    invokeMCP,
    
    // 项目/设备
    switchProject,
    sendDeviceCommand,
    
    // 快捷指令
    quick,
    
    // 控制
    cancel,
    reset,
  };
}

export default useCommands;
