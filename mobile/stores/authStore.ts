// 认证状态管理

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { tokenStorage, userStorage, appStorage } from '@/services/storage/mmkv';
import { UserInfo } from '@/types';

// MMKV 适配器
const mmkvStorage = {
  getItem: (name: string): string | null => {
    return appStorage.getString(name);
  },
  setItem: (name: string, value: string): void => {
    appStorage.setString(name, value);
  },
  removeItem: (name: string): void => {
    appStorage.remove(name);
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
        tokenStorage.setToken(token);
        set({ token, isLoggedIn: true });
      },
      
      setUserInfo: (userInfo: UserInfo) => {
        userStorage.setUserInfo(userInfo);
        set({ userInfo });
      },
      
      setLoading: (loading: boolean) => {
        set({ isLoading: loading });
      },
      
      login: (token: string, userInfo: UserInfo) => {
        tokenStorage.setToken(token);
        userStorage.setUserInfo(userInfo);
        set({ token, userInfo, isLoggedIn: true, isLoading: false });
      },
      
      logout: () => {
        tokenStorage.removeToken();
        userStorage.removeUserInfo();
        set({ token: null, userInfo: null, isLoggedIn: false });
      },
      
      updateUserInfo: (partial: Partial<UserInfo>) => {
        const current = get().userInfo;
        if (current) {
          const updated = { ...current, ...partial };
          userStorage.setUserInfo(updated);
          set({ userInfo: updated });
        }
      },
    }),
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => mmkvStorage),
      partialize: (state) => ({
        token: state.token,
        userInfo: state.userInfo,
        isLoggedIn: state.isLoggedIn,
      }),
    }
  )
);

// 初始化时从存储读取
export const initAuthStore = () => {
  const token = tokenStorage.getToken();
  const userInfo = userStorage.getUserInfo();
  
  if (token && userInfo) {
    useAuthStore.setState({
      token,
      userInfo,
      isLoggedIn: true,
    });
  }
};
