// 设备管理服务

import { deviceApi } from '@/services/api/devices';
import { Device, DeviceBindingRequest } from '@/types';
import { useDeviceStore } from '@/stores/deviceStore';
import i18n from '@/locales';

export class DeviceManager {
  // 获取设备列表
  static async fetchDevices(): Promise<Device[]> {
    const store = useDeviceStore.getState();
    store.setLoading(true);
    store.setError(null);

    try {
      const devices = await deviceApi.getDevices();
      console.log('[DeviceManager] Fetched devices:', devices);

      // 确保返回的是数组
      const safeDevices = Array.isArray(devices) ? devices : [];
      store.setDevices(safeDevices);

      // 自动修正：持久化的当前设备如果已不在列表中，选择第一个在线设备兜底
      const { currentDevice } = store;
      if (currentDevice && !safeDevices.some((d) => d.deviceKey === currentDevice.deviceKey)) {
        const fallback = safeDevices.find((d) => d.status === 'online') || safeDevices[0] || null;
        if (fallback) {
          console.log('[DeviceManager] Current device stale, auto-switch to:', fallback.deviceKey);
        }
        store.setCurrentDevice(fallback);
      }

      return safeDevices;
    } catch (error) {
      console.error('[DeviceManager] fetchDevices error:', error);
      const err = error instanceof Error ? error : new Error(i18n.t('devices.fetchFailed'));
      store.setError(err);
      store.setDevices([]);
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
  static async refreshDeviceStatus(deviceKey: string): Promise<Device> {
    const store = useDeviceStore.getState();
    
    try {
      const device = await deviceApi.getDeviceDetail(deviceKey);
      store.updateDevice(deviceKey, device);
      return device;
    } catch (error) {
      console.error('刷新设备状态失败:', error);
      throw error;
    }
  }

  // 发送设备指令
  static async sendCommand(
    deviceKey: string,
    commandType: string,
    params: Record<string, any> = {}
  ): Promise<any> {
    return deviceApi.sendCommand({
      deviceKey,
      command: {
        type: commandType,
        params,
      },
    });
  }

  // 更新设备在线状态
  static updateDeviceStatus(deviceKey: string, status: Device['status']): void {
    const store = useDeviceStore.getState();
    store.updateDevice(deviceKey, { 
      status,
      lastSeen: String(Date.now()),
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
