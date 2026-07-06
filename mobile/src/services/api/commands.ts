// 指令下达 API - 通过 Gateway 向 Desktop 下达指令
// 链路: Mobile → Gateway → Desktop (WebSocket)
// 聊天消息发送已迁移至 useDeviceControl.ts（sendToDevice）

import { api } from './client';

/** 通用指令响应 */
export interface ExecuteCommandResponse {
  code: number;
  message: string;
  data?: any;
  request_id?: string;
}

/**
 * 停止 Agent 执行
 * 统一走 /gateway/api/v1/message/send，信封类型 command.stop
 */
export async function stopExecution(
  threadId: string,
  deviceKey?: string
): Promise<ExecuteCommandResponse> {
  const envelope = {
    version: '2.0' as const,
    type: 'command.stop' as const,
    timestamp: Math.floor(Date.now() / 1000),
    source: { kind: 'mobile' as const },
    target: { kind: 'agent' as const, device_key: deviceKey },
    body: {
      thread_id: threadId,
    },
  };

  return api.post('/gateway/api/v1/message/send', {
    target_device_key: deviceKey,
    envelope,
  });
}

export const commandApi = {
  stopExecution,
};

export default commandApi;
