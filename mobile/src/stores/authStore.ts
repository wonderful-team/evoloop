// 认证状态管理

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { UserInfo } from '@/types';
import { api } from '@/services/api/client';

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
      
      setToken: async (token: string) => {
        set({ token, isLoggedIn: true });
        await AsyncStorage.setItem('token', token);
      },
      
      setUserInfo: (userInfo: UserInfo) => {
        set({ userInfo });
      },
      
      setLoading: (loading: boolean) => {
        set({ isLoading: loading });
      },
      
      login: async (token: string, userInfo: UserInfo) => {
        set({ token, userInfo, isLoggedIn: true, isLoading: false });
        // 同时保存到 AsyncStorage 供 API 客户端使用
        await AsyncStorage.setItem('token', token);
        await AsyncStorage.setItem('userInfo', JSON.stringify(userInfo));
      },
      
      logout: async () => {
        set({ token: null, userInfo: null, isLoggedIn: false });
        // 清除 AsyncStorage 中的 token
        await AsyncStorage.removeItem('token');
        await AsyncStorage.removeItem('userInfo');
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
      // 不持久化 isLoggedIn，由 initAuthStore 根据 token 有效性设置
      partialize: (state) => ({
        token: state.token,
        userInfo: state.userInfo,
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

// 初始化时验证并清除无效的登录状态
export const initAuthStore = async () => {
  console.log('[Auth] Starting initAuthStore...');
  let finalIsLoggedIn = false;
  try {
    // 等待 persist 恢复完成
    await new Promise(resolve => setTimeout(resolve, 100));

    // 从 store 获取当前状态（persist 恢复后的）
    let currentState;
    try {
      currentState = useAuthStore.getState();
      console.log('[Auth] Got store state');
    } catch (e) {
      console.error('[Auth] Failed to get store state:', e);
      return;
    }

    const token = currentState.token;
    const userInfo = currentState.userInfo;

    console.log('[Auth] Current store state - token:', token ? 'exists' : 'null', 'userInfo:', userInfo ? 'exists' : 'null', 'isLoggedIn:', currentState.isLoggedIn);

    // 初始设置为未登录，验证通过后自动登录
    useAuthStore.setState({ isLoggedIn: false });
    console.log('[Auth] Reset isLoggedIn to false');
    finalIsLoggedIn = false;

    // 如果有 token，验证其有效性
    if (token) {
      try {
        console.log('[Auth] Validating token...');
        await api.get('/member/api/member/info');
        console.log('[Auth] Token valid, auto login');
        useAuthStore.setState({ isLoggedIn: true });
        finalIsLoggedIn = true;
      } catch (verifyError) {
        console.log('[Auth] Token invalid or validation failed:', verifyError);
        useAuthStore.setState({ token: null, userInfo: null, isLoggedIn: false });
        await AsyncStorage.removeItem('token');
        await AsyncStorage.removeItem('userInfo');
      }
    }
  } catch (error) {
    console.error('[Auth] Init auth store error:', error);
  }
  console.log('[Auth] initAuthStore completed, final isLoggedIn:', finalIsLoggedIn);
};
