// 设备管理 Hook

import { useEffect, useCallback } from 'react';
import { DeviceManager } from '@/services/devices/DeviceManager';
import { useDeviceStore } from '@/stores/deviceStore';
import { Device } from '@/types';

interface UseDevicesOptions {
  autoFetch?: boolean;
}

export function useDevices(options: UseDevicesOptions = {}) {
  const { autoFetch = true } = options;
  const store = useDeviceStore();
  const { devices, currentDevice, isLoading, error } = store;

  // 自动获取设备列表
  useEffect(() => {
    if (autoFetch) {
      DeviceManager.fetchDevices().catch(console.error);
    }
  }, [autoFetch]);

  // 刷新设备列表
  const refresh = useCallback(async () => {
    return DeviceManager.fetchDevices();
  }, []);

  // 绑定设备
  const bindDevice = useCallback(async (deviceKey: string) => {
    return DeviceManager.bindDevice(deviceKey);
  }, []);

  // 刷新设备状态
  const refreshDevice = useCallback(async (deviceId: string) => {
    return DeviceManager.refreshDeviceStatus(deviceId);
  }, []);

  // 发送指令
  const sendCommand = useCallback(
    async (deviceId: string, commandType: string, params?: Record<string, any>) => {
      return DeviceManager.sendCommand(deviceId, commandType, params);
    },
    []
  );

  // 切换当前设备
  const setCurrentDevice = useCallback((device: Device | null) => {
    DeviceManager.setCurrentDevice(device);
  }, []);

  // 获取在线设备数
  const onlineCount = devices.filter((d) => d.status === 'online').length;

  return {
    devices,
    currentDevice,
    isLoading,
    error,
    onlineCount,
    totalCount: devices.length,
    refresh,
    bindDevice,
    refreshDevice,
    sendCommand,
    setCurrentDevice,
  };
}

// 单个设备 Hook
export function useDevice(deviceId: string) {
  const store = useDeviceStore();
  const device = store.devices.find((d) => d.id === deviceId);

  const refresh = useCallback(async () => {
    if (!deviceId) return null;
    return DeviceManager.refreshDeviceStatus(deviceId);
  }, [deviceId]);

  const sendCommand = useCallback(
    async (commandType: string, params?: Record<string, any>) => {
      if (!deviceId) return null;
      return DeviceManager.sendCommand(deviceId, commandType, params);
    },
    [deviceId]
  );

  return {
    device,
    refresh,
    sendCommand,
  };
}
