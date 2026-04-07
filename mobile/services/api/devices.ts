// 设备 API

import { api } from './client';
import { GATEWAY_API } from '@/constants/api';
import {
  ApiResponse,
  Device,
  DeviceBindingRequest,
  DeviceCommandRequest,
} from '@/types';

export const deviceApi = {
  // 获取设备列表
  getDevices: async (): Promise<Device[]> => {
    const response = await api.get<ApiResponse<Device[]>>(
      GATEWAY_API.DEVICES
    );
    return response.data;
  },

  // 绑定设备
  bindDevice: async (data: DeviceBindingRequest): Promise<Device> => {
    const response = await api.post<ApiResponse<Device>>(
      GATEWAY_API.DEVICE_BIND,
      data
    );
    return response.data;
  },

  // 获取设备详情
  getDeviceDetail: async (id: string): Promise<Device> => {
    const response = await api.get<ApiResponse<Device>>(
      GATEWAY_API.DEVICE_DETAIL(id)
    );
    return response.data;
  },

  // 发送设备指令
  sendCommand: async (data: DeviceCommandRequest): Promise<any> => {
    const response = await api.post<ApiResponse<any>>(
      GATEWAY_API.COMMAND_SEND,
      data
    );
    return response.data;
  },
};
