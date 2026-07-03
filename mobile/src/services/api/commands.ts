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
 */
export async function stopExecution(
  threadId: string,
  deviceKey?: string
): Promise<ExecuteCommandResponse> {
  return api.post(`/gateway/api/v1/conversations/${threadId}/stop`, {}, {
    params: { device_key: deviceKey }
  });
}

export const commandApi = {
  stopExecution,
};

export default commandApi;
