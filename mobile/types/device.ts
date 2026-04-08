// 设备相关类型
// 注意: device_id 有两种形式:
// 1. device_key (string UUID): 本地生成,用于 WebSocket 连接和 Gateway 路由
// 2. numeric_device_id (number): MC 分配,用于后端 API 调用

export type DeviceStatus = 'online' | 'offline' | 'busy';
export type DeviceType = 'desktop' | 'mobile';

export interface Device {
  id: string;                    // device_key (UUID) - 本地标识,用于 WebSocket
  numeric_device_id?: number;    // MC 分配的 device_id - 用于 API 调用 (来自 Gateway)
  name: string;
  type: DeviceType;
  status: DeviceStatus;
  osInfo: string;
  currentProject?: {
    id: number;
    name: string;
  };
  lastSeen: number;
  capabilities: string[];
}

export interface DeviceBindingRequest {
  deviceKey: string;
}

export interface DeviceCommand {
  type: string;
  params: Record<string, any>;
}

export interface DeviceCommandRequest {
  deviceId: string;              // device_key for Gateway routing
  numeric_device_id?: number;    // MC device_id for backend API calls
  command: DeviceCommand;
}
