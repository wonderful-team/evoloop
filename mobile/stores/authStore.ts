// 认证状态管理

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { UserInfo } from '@/types';

// AsyncStorage 适配器 for Zustand
const asyncStorageAdapter = {
  getItem: async (name: string): Promise<string | null> => {
    return AsyncStorage.getItem(name);
  },
  setItem: async (name: string, value: string): Promise<void> => {
    await AsyncStorage.setItem(name, value);
  },
  removeItem: async (name: string): Promise<void> => {
    await AsyncStorage.removeItem(name);
  },
};

interface AuthState {
  // 状态
  token: string | null;
  userInfo: UserInfo | null;
  isLoggedIn: boolean;
  isLoading: boolean;
  
  // Actions
  setToken: (token: string) => void;
  setUserInfo: (userInfo: UserInfo) => void;
  setLoading: (loading: boolean) => void;
  login: (token: string, userInfo: UserInfo) => void;
  logout: () => void;
  updateUserInfo: (partial: Partial<UserInfo>) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      userInfo: null,
      isLoggedIn: false,
      isLoading: false,
      
      setToken: (token: string) => {
        set({ token, isLoggedIn: true });
      },
      
      setUserInfo: (userInfo: UserInfo) => {
        set({ userInfo });
      },
      
      setLoading: (loading: boolean) => {
        set({ isLoading: loading });
      },
      
      login: (token: string, userInfo: UserInfo) => {
        set({ token, userInfo, isLoggedIn: true, isLoading: false });
      },
      
      logout: () => {
        set({ token: null, userInfo: null, isLoggedIn: false });
      },
      
      updateUserInfo: (partial: Partial<UserInfo>) => {
        const current = get().userInfo;
        if (current) {
          const updated = { ...current, ...partial };
          set({ userInfo: updated });
        }
      },
    }),
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => asyncStorageAdapter),
      partialize: (state) => ({
        token: state.token,
        userInfo: state.userInfo,
        isLoggedIn: state.isLoggedIn,
      }),
    }
  )
);

// Token 存储辅助函数
export const tokenStorage = {
  getToken: async (): Promise<string | null> => {
    return AsyncStorage.getItem('token');
  },
  setToken: async (token: string): Promise<void> => {
    await AsyncStorage.setItem('token', token);
  },
  removeToken: async (): Promise<void> => {
    await AsyncStorage.removeItem('token');
  },
};

// 用户信息存储辅助函数
export const userStorage = {
  getUserInfo: async () => {
    const data = await AsyncStorage.getItem('userInfo');
    return data ? JSON.parse(data) : null;
  },
  setUserInfo: async (userInfo: any): Promise<void> => {
    await AsyncStorage.setItem('userInfo', JSON.stringify(userInfo));
  },
  removeUserInfo: async (): Promise<void> => {
    await AsyncStorage.removeItem('userInfo');
  },
};

// 通用存储
export const appStorage = {
  getString: async (key: string): Promise<string | null> => {
    return AsyncStorage.getItem(key);
  },
  setString: async (key: string, value: string): Promise<void> => {
    await AsyncStorage.setItem(key, value);
  },
  remove: async (key: string): Promise<void> => {
    await AsyncStorage.removeItem(key);
  },
};

// 初始化时从存储读取
export const initAuthStore = async () => {
  try {
    const token = await AsyncStorage.getItem('token');
    const userInfoStr = await AsyncStorage.getItem('userInfo');
    const userInfo = userInfoStr ? JSON.parse(userInfoStr) : null;
    
    if (token && userInfo) {
      useAuthStore.setState({
        token,
        userInfo,
        isLoggedIn: true,
      });
    }
  } catch (error) {
    console.error('Init auth store error:', error);
  }
};
