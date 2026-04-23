// 设备状态管理

import { create } from 'zustand';
import { Device } from '@/types';

interface DeviceState {
  devices: Device[];
  currentDevice: Device | null;
  isLoading: boolean;
  error: Error | null;

  setDevices: (devices: Device[]) => void;
  setCurrentDevice: (device: Device | null) => void;
  addDevice: (device: Device) => void;
  updateDevice: (deviceKey: string, updates: Partial<Device>) => void;
  removeDevice: (deviceKey: string) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: Error | null) => void;
}

export const useDeviceStore = create<DeviceState>((set, get) => ({
  devices: [],
  currentDevice: null,
  isLoading: false,
  error: null,

  setDevices: (devices) => set({ devices }),

  setCurrentDevice: (device) => set({ currentDevice: device }),

  addDevice: (device) => {
    const { devices } = get();
    set({ devices: [...devices, device] });
  },

  updateDevice: (deviceKey, updates) => {
    const { devices } = get();
    set({
      devices: devices.map((d) =>
        d.deviceKey === deviceKey ? { ...d, ...updates } : d
      ),
    });
  },

  removeDevice: (deviceKey) => {
    const { devices, currentDevice } = get();
    set({
      devices: (devices || []).filter((d) => d.deviceKey !== deviceKey),
      currentDevice: currentDevice?.deviceKey === deviceKey ? null : currentDevice,
    });
  },

  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),
}));
