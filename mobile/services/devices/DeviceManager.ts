// 设备管理服务

import { deviceApi } from '@/services/api/devices';
import { Device, DeviceBindingRequest } from '@/types';
import { useDeviceStore } from '@/stores/deviceStore';

export class DeviceManager {
  // 获取设备列表
  static async fetchDevices(): Promise<Device[]> {
    const store = useDeviceStore.getState();
    store.setLoading(true);
    store.setError(null);

    try {
      const devices = await deviceApi.getDevices();
      store.setDevices(devices);
      return devices;
    } catch (error) {
      const err = error instanceof Error ? error : new Error('获取设备列表失败');
      store.setError(err);
      throw err;
    } finally {
      store.setLoading(false);
    }
  }

  // 绑定设备
  static async bindDevice(deviceKey: string): Promise<Device> {
    const store = useDeviceStore.getState();
    store.setLoading(true);

    try {
      const device = await deviceApi.bindDevice({ deviceKey });
      store.addDevice(device);
      return device;
    } finally {
      store.setLoading(false);
    }
  }

  // 刷新设备状态
  static async refreshDeviceStatus(deviceId: string): Promise<Device> {
    const store = useDeviceStore.getState();
    
    try {
      const device = await deviceApi.getDeviceDetail(deviceId);
      store.updateDevice(deviceId, device);
      return device;
    } catch (error) {
      console.error('刷新设备状态失败:', error);
      throw error;
    }
  }

  // 发送设备指令
  static async sendCommand(
    deviceId: string,
    commandType: string,
    params: Record<string, any> = {}
  ): Promise<any> {
    return deviceApi.sendCommand({
      deviceId,
      command: {
        type: commandType,
        params,
      },
    });
  }

  // 更新设备在线状态
  static updateDeviceStatus(deviceId: string, status: Device['status']): void {
    const store = useDeviceStore.getState();
    store.updateDevice(deviceId, { 
      status,
      lastSeen: Date.now(),
    });
  }

  // 获取当前设备
  static getCurrentDevice(): Device | null {
    return useDeviceStore.getState().currentDevice;
  }

  // 设置当前设备
  static setCurrentDevice(device: Device | null): void {
    const store = useDeviceStore.getState();
    store.setCurrentDevice(device);
  }
}
