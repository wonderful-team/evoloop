// MMKV 存储服务

import { MMKV } from 'react-native-mmkv';

// 创建 MMKV 实例
export const storage = new MMKV({
  id: 'evoloop-storage',
  encryptionKey: 'evoloop-secure-storage-key',
});

// Token 存储
export const tokenStorage = {
  getToken: (): string | null => {
    return storage.getString('token') || null;
  },
  
  setToken: (token: string): void => {
    storage.set('token', token);
  },
  
  removeToken: (): void => {
    storage.delete('token');
  },
};

// 用户信息存储
export const userStorage = {
  getUserInfo: () => {
    const data = storage.getString('userInfo');
    return data ? JSON.parse(data) : null;
  },
  
  setUserInfo: (userInfo: any): void => {
    storage.set('userInfo', JSON.stringify(userInfo));
  },
  
  removeUserInfo: (): void => {
    storage.delete('userInfo');
  },
};

// 通用存储方法
export const appStorage = {
  getString: (key: string): string | null => {
    return storage.getString(key) || null;
  },
  
  setString: (key: string, value: string): void => {
    storage.set(key, value);
  },
  
  getNumber: (key: number): number => {
    return storage.getNumber(key) || 0;
  },
  
  setNumber: (key: string, value: number): void => {
    storage.set(key, value);
  },
  
  getBoolean: (key: string): boolean => {
    return storage.getBoolean(key) || false;
  },
  
  setBoolean: (key: string, value: boolean): void => {
    storage.set(key, value);
  },
  
  getObject: <T = any>(key: string): T | null => {
    const data = storage.getString(key);
    return data ? JSON.parse(data) : null;
  },
  
  setObject: (key: string, value: any): void => {
    storage.set(key, JSON.stringify(value));
  },
  
  remove: (key: string): void => {
    storage.delete(key);
  },
  
  clearAll: (): void => {
    storage.clearAll();
  },
};
