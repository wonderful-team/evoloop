// 设备状态管理

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import AsyncStorage from '@react-native-async-storage/async-storage';
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
  updateDeviceStatus: (deviceKey: string, status: Device['status']) => void;
  removeDevice: (deviceKey: string) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: Error | null) => void;
  reset: () => void;
}

export const useDeviceStore = create<DeviceState>()(
  persist(
    (set, get) => ({
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

      updateDeviceStatus: (deviceKey, status) => {
        const { devices } = get();
        const target = devices.find((d) => d.deviceKey === deviceKey);
        if (!target) return;

        const lastSeen = status === 'online' ? String(Date.now() / 1000) : target.lastSeen;
        set({
          devices: devices.map((d) =>
            d.deviceKey === deviceKey ? { ...d, status, lastSeen } : d
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
      reset: () => set({ devices: [], currentDevice: null, isLoading: false, error: null }),
    }),
    {
      name: 'device-storage',
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (state) => ({
        currentDevice: state.currentDevice,
      }),
    }
  )
);
