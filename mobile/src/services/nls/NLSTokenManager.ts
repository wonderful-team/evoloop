// NLS Token 管理器
// 从 Gateway 获取临时 Token 和 AppKey

import AsyncStorage from '@react-native-async-storage/async-storage';
import { GATEWAY_API } from '@/constants/api';
import { api } from '../api/client';

interface TokenResponse {
  token: string;
  expire_time: number;
  app_key: string;
}

class NLSTokenManager {
  private token: string = '';
  private expireTime: number = 0;
  private appKey: string = '';
  private isFetching: boolean = false;
  private fetchPromise: Promise<string> | null = null;

  /**
   * 从 Gateway 获取 Token
   */
  async fetchTokenFromGateway(): Promise<string> {
    try {
      console.log('[NLS] 从 Gateway 获取 Token...');

      const response = await api.get<TokenResponse>(GATEWAY_API.NLS_TOKEN);

      if (response.token) {
        this.token = response.token;
        this.expireTime = response.expire_time || Date.now() + 3600 * 1000;
        this.appKey = response.app_key || '';

        await this.cacheToken();

        console.log('[NLS] Gateway Token 获取成功');
        return this.token;
      }

      throw new Error('Gateway 返回的 Token 无效');
    } catch (error) {
      console.error('[NLS] 从 Gateway 获取 Token 失败:', error);
      throw error;
    }
  }

  /**
   * 获取有效 Token
   */
  async getValidToken(): Promise<string> {
    if (this.token && this.expireTime - Date.now() > 5 * 60 * 1000) {
      console.log('[NLS] 使用缓存的 Token');
      return this.token;
    }

    if (this.isFetching && this.fetchPromise) {
      return this.fetchPromise;
    }

    this.isFetching = true;
    this.fetchPromise = this.doFetchToken();

    try {
      const token = await this.fetchPromise;
      return token;
    } finally {
      this.isFetching = false;
      this.fetchPromise = null;
    }
  }

  /**
   * 实际获取 Token
   */
  private async doFetchToken(): Promise<string> {
    try {
      await this.loadCachedToken();
      if (this.token && this.expireTime - Date.now() > 5 * 60 * 1000) {
        console.log('[NLS] 使用本地缓存的 Token');
        return this.token;
      }
    } catch (e) {
      // 缓存读取失败，继续获取新 Token
    }

    return await this.fetchTokenFromGateway();
  }

  /**
   * 缓存 Token
   */
  private async cacheToken(): Promise<void> {
    try {
      await AsyncStorage.setItem('nls_token', JSON.stringify({
        token: this.token,
        expireTime: this.expireTime,
        appKey: this.appKey,
      }));
    } catch (e) {
      console.warn('[NLS] Token 缓存失败:', e);
    }
  }

  /**
   * 加载缓存的 Token
   */
  private async loadCachedToken(): Promise<void> {
    try {
      const cached = await AsyncStorage.getItem('nls_token');
      if (cached) {
        const data = JSON.parse(cached);
        this.token = data.token;
        this.expireTime = data.expireTime;
        this.appKey = data.appKey || '';
      }
    } catch (e) {
      console.warn('[NLS] Token 缓存读取失败:', e);
    }
  }

  /**
   * 清除 Token
   */
  clearToken(): void {
    this.token = '';
    this.expireTime = 0;
    this.appKey = '';
    AsyncStorage.removeItem('nls_token').catch(console.error);
  }

  /**
   * 获取 Token 过期时间
   */
  getExpireTime(): number {
    return this.expireTime;
  }

  /**
   * 检查 Token 是否有效
   */
  isTokenValid(): boolean {
    return !!this.token && this.expireTime > Date.now();
  }

  /**
   * 获取 AppKey
   */
  getAppKey(): string {
    return this.appKey;
  }
}

export const nlsTokenManager = new NLSTokenManager();
