// 设备管理 Hook

import { useEffect, useCallback, useRef } from 'react';
import { AppState } from 'react-native';
import { DeviceManager } from '@/services/devices/DeviceManager';
import { useDeviceStore } from '@/stores/deviceStore';
import { Device } from '@/types';

interface UseDevicesOptions {
  autoFetch?: boolean;
  refetchInterval?: number; // 轮询间隔（毫秒），默认 10000
}

export function useDevices(options: UseDevicesOptions = {}) {
  const { autoFetch = true, refetchInterval = 10000 } = options;
  const store = useDeviceStore();
  const { devices, currentDevice, isLoading, error } = store;
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  // 确保 devices 是数组
  const safeDevices = devices || [];

  // 启动轮询
  const startPolling = useCallback(() => {
    if (intervalRef.current) return;
    intervalRef.current = setInterval(() => {
      DeviceManager.fetchDevices().catch(console.error);
    }, refetchInterval);
  }, [refetchInterval]);

  // 停止轮询
  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  // 自动获取 + 轮询（根据 App 前后台状态启停）
  useEffect(() => {
    if (!autoFetch) return;

    // 首次加载
    DeviceManager.fetchDevices().catch(console.error);
    startPolling();

    // 监听前后台切换
    const subscription = AppState.addEventListener('change', (nextAppState) => {
      if (nextAppState === 'active') {
        // 回到前台：立即刷新 + 启动轮询
        DeviceManager.fetchDevices().catch(console.error);
        startPolling();
      } else {
        // 进入后台：停止轮询
        stopPolling();
      }
    });

    return () => {
      subscription.remove();
      stopPolling();
    };
  }, [autoFetch, startPolling, stopPolling]);

  // 刷新设备列表
  const refresh = useCallback(async () => {
    return DeviceManager.fetchDevices();
  }, []);

  // 绑定设备
  const bindDevice = useCallback(async (deviceKey: string) => {
    return DeviceManager.bindDevice(deviceKey);
  }, []);

  // 刷新设备状态
  const refreshDevice = useCallback(async (deviceKey: string) => {
    return DeviceManager.refreshDeviceStatus(deviceKey);
  }, []);

  // 发送指令
  const sendCommand = useCallback(
    async (deviceKey: string, commandType: string, params?: Record<string, any>) => {
      return DeviceManager.sendCommand(deviceKey, commandType, params);
    },
    []
  );

  // 切换当前设备
  const setCurrentDevice = useCallback((device: Device | null) => {
    DeviceManager.setCurrentDevice(device);
  }, []);

  // 获取在线设备数
  const onlineCount = safeDevices.filter((d) => d.status === 'online').length;

  return {
    devices: safeDevices,
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
export function useDevice(deviceKey: string) {
  const store = useDeviceStore();
  const device = store.devices.find((d) => d.deviceKey === deviceKey);

  const refresh = useCallback(async () => {
    if (!deviceKey) return null;
    return DeviceManager.refreshDeviceStatus(deviceKey);
  }, [deviceKey]);

  const sendCommand = useCallback(
    async (commandType: string, params?: Record<string, any>) => {
      if (!deviceKey) return null;
      return DeviceManager.sendCommand(deviceKey, commandType, params);
    },
    [deviceKey]
  );

  return {
    device,
    refresh,
    sendCommand,
  };
}
