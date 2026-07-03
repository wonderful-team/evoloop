// 设备管理 Hook

import { useEffect, useCallback, useRef, useMemo } from 'react';
import { AppState } from 'react-native';
import { DeviceManager } from '@/services/devices/DeviceManager';
import { useDeviceStore } from '@/stores/deviceStore';
import { useConversationStore } from '@/stores/conversationStore';
import { Device } from '@/types';
import { GatewayClient } from '@/services/gateway/GatewayClient';
import { GatewayMessageType } from '@/services/gateway/types';

interface UseDevicesOptions {
  autoFetch?: boolean;
  // 轮询间隔（毫秒），默认 0 表示禁用轮询，依赖 Gateway WebSocket 实时推送
  refetchInterval?: number;
}

export function useDevices(options: UseDevicesOptions = {}) {
  const { autoFetch = true, refetchInterval = 10000 } = options;
  const store = useDeviceStore();
  const { devices, currentDevice, isLoading, error } = store;
  const { unreadCounts, conversationDeviceMap } = useConversationStore();
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  // 确保 devices 是数组
  const safeDevices = devices || [];

  // 计算每个设备的未读总数
  const devicesWithUnread = useMemo(() => {
    return safeDevices.map((device) => {
      const conversationIds = conversationDeviceMap[device.deviceKey] || [];
      const unreadCount = conversationIds.reduce(
        (sum, id) => sum + (unreadCounts[id] || 0),
        0
      );
      return { ...device, unreadCount };
    });
  }, [safeDevices, unreadCounts, conversationDeviceMap]);

  // 启动轮询（已禁用：设备状态通过 Gateway WebSocket 实时推送）
  const startPolling = useCallback(() => {
    // no-op: 保留 API 兼容性，但不再使用轮询
  }, []);

  // 停止轮询
  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  // 自动获取（仅在进入前台时拉取全量，后续靠 Gateway WebSocket 推送增量更新）
  useEffect(() => {
    if (!autoFetch) return;

    // 首次加载
    DeviceManager.fetchDevices().catch(console.error);

    // 监听前后台切换：回到前台时刷新一次，进入后台不做处理
    const subscription = AppState.addEventListener('change', (nextAppState) => {
      if (nextAppState === 'active') {
        DeviceManager.fetchDevices().catch(console.error);
      }
    });

    return () => {
      subscription.remove();
      stopPolling();
    };
  }, [autoFetch, stopPolling]);

  // 监听 Gateway 推送的设备状态变化
  useEffect(() => {
    if (!autoFetch) return;

    const gateway = GatewayClient.getInstance();

    const handleDeviceStatusUpdate = (message: any) => {
      const data = message?.data;
      if (!data) return;

      const { device_key, online } = data;
      if (!device_key) return;

      const status = online ? 'online' : 'offline';
      store.updateDeviceStatus(device_key, status);
    };

    const handleMessage = (message: { type: string; data: any }) => {
      if (message.type === 'device.status') {
        handleDeviceStatusUpdate(message);
      }
    };

    gateway.on('message', handleMessage);

    return () => {
      gateway.off('message', handleMessage);
    };
  }, [autoFetch, store]);

  // 监听 devices/currentDevice 变化：持久化设备若已不在列表中，自动切换到第一个在线设备
  useEffect(() => {
    if (currentDevice && !safeDevices.some((d) => d.deviceKey === currentDevice.deviceKey)) {
      const fallback = safeDevices.find((d) => d.status === 'online') || safeDevices[0] || null;
      if (fallback?.deviceKey !== currentDevice.deviceKey) {
        console.log('[useDevices] currentDevice stale, auto-switch to:', fallback?.deviceKey);
        store.setCurrentDevice(fallback);
      }
    }
  }, [safeDevices, currentDevice, store]);

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
    devices: devicesWithUnread,
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
