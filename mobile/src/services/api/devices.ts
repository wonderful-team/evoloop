// 设备 API

import { api } from './client';
import {
  ApiResponse,
  Device,
  DeviceBindingRequest,
  DeviceCommandRequest,
} from '@/types';
import i18n from '@/locales';

// 后端设备数据接口
interface BackendDevice {
  device_key: string;
  device_name: string;
  device_type?: string;
  os_info?: string;
  status: number | string;
  client_id?: string;
  last_heartbeat?: number;
  last_active_at?: number;
  create_time?: number;
}

// 将后端设备数据映射为前端 Device 类型
const mapBackendDevice = (backendDevice: BackendDevice): Device => {
  // 处理状态：后端是 0/1，前端是 'online'/'offline'/'busy'
  let status: Device['status'] = 'offline';
  const rawStatus = backendDevice.status;
  if (rawStatus === 1 || rawStatus === '1' || rawStatus === 'online') {
    status = 'online';
  } else if (rawStatus === 'busy') {
    status = 'busy';
  }

  return {
    deviceKey: String(backendDevice.device_key),
    name: backendDevice.device_name || i18n.t('devices.unnamedDevice'),
    status,
    type: backendDevice.device_type || 'desktop',
    lastSeen: backendDevice.last_heartbeat
      ? String(backendDevice.last_heartbeat)
      : (backendDevice.last_active_at ? String(backendDevice.last_active_at) : undefined),
  };
};

// 处理 API 响应（可能是包装对象或直接的数组）
const extractDevices = (response: any): Device[] => {
  console.log('[deviceApi] Processing response type:', typeof response, Array.isArray(response) ? 'array' : 'object');

  if (!response) {
    return [];
  }

  // 如果是数组，直接映射
  if (Array.isArray(response)) {
    console.log('[deviceApi] Response is array, mapping', response.length, 'devices');
    const mapped = (response as BackendDevice[]).map(mapBackendDevice);
    console.log('[deviceApi] First mapped device:', mapped[0]);
    return mapped;
  }

  // 如果是包装对象 { code, data, message }
  if (typeof response === 'object' && 'data' in response) {
    const data = response.data;
    // Gateway /api/v1/devices 返回 { devices: [...], total }
    if (data && typeof data === 'object' && 'devices' in data && Array.isArray(data.devices)) {
      console.log('[deviceApi] Response is Gateway device wrapper, mapping', data.devices.length, 'devices');
      const mapped = (data.devices as BackendDevice[]).map(mapBackendDevice);
      console.log('[deviceApi] First mapped device:', mapped[0]);
      return mapped;
    }
    if (Array.isArray(data)) {
      console.log('[deviceApi] Response is wrapper, mapping', data.length, 'devices');
      const mapped = data.map(mapBackendDevice);
      console.log('[deviceApi] First mapped device:', mapped[0]);
      return mapped;
    }
  }

  console.warn('[deviceApi] Unexpected response structure:', response);
  return [];
};

export const deviceApi = {
  // 获取设备列表 (从 Gateway 获取当前在线设备)
  getDevices: async (): Promise<Device[]> => {
    const response = await api.get<BackendDevice[] | ApiResponse<BackendDevice[]>>(
      `/gateway/api/v1/devices`
    );
    return extractDevices(response);
  },

  // 绑定设备 (扫码绑定)
  bindDevice: async (data: DeviceBindingRequest): Promise<Device> => {
    const response = await api.post<ApiResponse<BackendDevice>>(
      `/member/evolooplink/api/device/bind`,
      data
    );
    return mapBackendDevice(response.data);
  },

  // 获取设备详情
  getDeviceDetail: async (deviceKey: string): Promise<Device> => {
    const response = await api.get<ApiResponse<BackendDevice>>(
      `/member/evolooplink/api/device/detail?device_key=${deviceKey}`
    );
    return mapBackendDevice(response.data);
  },

  // 解绑设备
  unbindDevice: async (deviceKey: string): Promise<void> => {
    await api.post(`/member/evolooplink/api/device/unbind`, { device_key: deviceKey });
  },

  // 发送设备指令 (直接通过 Go Gateway 执行，绕过 PHP 业务网关)
  sendCommand: async (data: DeviceCommandRequest): Promise<any> => {
    const response = await api.post<ApiResponse<any>>(
      `/gateway/api/v1/command/send`,
      {
        device_key: data.deviceKey,
        command_type: data.command.type,
        content: data.command.params,
      }
    );
    return response.data;
  },
};
