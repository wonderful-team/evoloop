// 应用设置状态管理

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import AsyncStorage from '@react-native-async-storage/async-storage';

interface Settings {
  autoSpeak: boolean;
  voiceSpeed: number;
  selectedVoice: string;
  theme: 'light' | 'dark' | 'system';
  language: string;
}

interface SettingsState {
  settings: Settings;

  // Actions
  setSetting: <K extends keyof Settings>(key: K, value: Settings[K]) => void;
  setSettings: (settings: Partial<Settings>) => void;
  resetSettings: () => void;
}

const DEFAULT_SETTINGS: Settings = {
  autoSpeak: false,
  voiceSpeed: 1.0,
  selectedVoice: 'zh-CN-XiaoxiaoNeural',
  theme: 'system',
  language: 'zh-CN',
};

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set, get) => ({
      settings: DEFAULT_SETTINGS,

      setSetting: (key, value) => {
        set((state) => ({
          settings: {
            ...state.settings,
            [key]: value,
          },
        }));
      },

      setSettings: (newSettings) => {
        set((state) => ({
          settings: {
            ...state.settings,
            ...newSettings,
          },
        }));
      },

      resetSettings: () => {
        set({ settings: DEFAULT_SETTINGS });
      },
    }),
    {
      name: 'settings-storage',
      storage: createJSONStorage(() => AsyncStorage),
    }
  )
);
