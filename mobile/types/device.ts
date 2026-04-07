// 设备相关类型

export type DeviceStatus = 'online' | 'offline' | 'busy';
export type DeviceType = 'desktop' | 'mobile';

export interface Device {
  id: string;
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
  deviceId: string;
  command: DeviceCommand;
}
