// Axios API 客户端

import axios, { AxiosError, AxiosRequestConfig, AxiosResponse } from 'axios';
import { API_CONFIG } from '@/constants/config';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { handleApiError, isAuthError } from '@/utils/error';
import { checkIsBenefitError, handleBenefitError, convertToBenefitError } from '@/utils/subscriptionErrors';
import { router } from 'expo-router';

// 权益错误回调（用于全局监听）
type BenefitErrorCallback = (error: { title: string; message: string; action?: { label: string; onPress: () => void } }) => void;
let benefitErrorCallback: BenefitErrorCallback | null = null;

/**
 * 设置权益错误回调
 * 通常在 App 根组件中设置，用于显示全局升级提示
 */
export function setBenefitErrorCallback(callback: BenefitErrorCallback) {
  benefitErrorCallback = callback;
}

/**
 * 清除权益错误回调
 */
export function clearBenefitErrorCallback() {
  benefitErrorCallback = null;
}

// 创建 axios 实例
const apiClient = axios.create({
  baseURL: API_CONFIG.baseURL,
  timeout: API_CONFIG.timeout,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
});

// 请求队列（用于 token 刷新）
let isRefreshing = false;
let refreshSubscribers: Array<(token: string) => void> = [];

// 订阅 token 刷新
const subscribeTokenRefresh = (callback: (token: string) => void) => {
  refreshSubscribers.push(callback);
};

// 通知所有订阅者
const onTokenRefreshed = (token: string) => {
  refreshSubscribers.forEach((callback) => callback(token));
  refreshSubscribers = [];
};

// 请求拦截器
apiClient.interceptors.request.use(
  async (config) => {
    const token = await AsyncStorage.getItem('token');
    
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    
    // URL 前缀处理 - 根据路径前缀设置正确的 baseURL
    const originalUrl = config.url || '';
    
    if (originalUrl.startsWith('/gateway')) {
      config.baseURL = `${API_CONFIG.baseURL}/gateway`;
      // 移除 /gateway 前缀，因为 baseURL 已经包含
      config.url = originalUrl.replace('/gateway', '');
    } else if (originalUrl.startsWith('/member')) {
      config.baseURL = `${API_CONFIG.baseURL}/member`;
      // 移除 /member 前缀，因为 baseURL 已经包含
      config.url = originalUrl.replace('/member', '');
    }
    
    console.log(`API Request: ${config.method?.toUpperCase()} ${config.baseURL}${config.url}`);
    
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器
apiClient.interceptors.response.use(
  (response: AxiosResponse) => {
    // 统一返回 data 字段
    console.log(`API Response: ${response.config.url}`, response.data);
    return response.data;
  },
  async (error: AxiosError) => {
    const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean };
    
    console.error('API Error:', error.response?.status, error.response?.data);
    
    if (!originalRequest) {
      return Promise.reject(handleApiError(error));
    }
    
    // 401 错误处理
    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        // 等待 token 刷新
        return new Promise((resolve) => {
          subscribeTokenRefresh((token: string) => {
            originalRequest.headers = originalRequest.headers || {};
            originalRequest.headers.Authorization = `Bearer ${token}`;
            resolve(apiClient(originalRequest));
          });
        });
      }
      
      originalRequest._retry = true;
      isRefreshing = true;
      
      try {
        // 这里可以实现 token 刷新逻辑
        // const newToken = await refreshToken();
        // tokenStorage.setToken(newToken);
        // onTokenRefreshed(newToken);
        // originalRequest.headers.Authorization = `Bearer ${newToken}`;
        // return apiClient(originalRequest);
        
        // 目前直接跳转到登录
        await AsyncStorage.removeItem('token');
        router.replace('/(auth)/login');
        return Promise.reject(handleApiError(error));
      } catch (refreshError) {
        await AsyncStorage.removeItem('token');
        router.replace('/(auth)/login');
        return Promise.reject(handleApiError(refreshError));
      } finally {
        isRefreshing = false;
      }
    }
    
    // 403 权益错误处理
    if (error.response?.status === 403) {
      const responseData = error.response.data;
      
      // 检查是否为权益错误
      if (checkIsBenefitError({ ...responseData, status: 403 })) {
        const errorInfo = handleBenefitError(responseData);
        
        // 触发全局回调（如果设置了）
        if (benefitErrorCallback && errorInfo.isBenefitError) {
          benefitErrorCallback({
            title: errorInfo.title,
            message: errorInfo.message,
            action: errorInfo.action,
          });
        }
        
        // 转换为 BenefitRequiredError
        const benefitError = convertToBenefitError(error);
        if (benefitError) {
          return Promise.reject(benefitError);
        }
      }
    }
    
    return Promise.reject(handleApiError(error));
  }
);

// 封装请求方法
export const api = {
  get: <T = any>(url: string, config?: AxiosRequestConfig): Promise<T> => {
    return apiClient.get(url, config);
  },
  
  post: <T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> => {
    return apiClient.post(url, data, config);
  },
  
  put: <T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> => {
    return apiClient.put(url, data, config);
  },
  
  delete: <T = any>(url: string, config?: AxiosRequestConfig): Promise<T> => {
    return apiClient.delete(url, config);
  },
  
  patch: <T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> => {
    return apiClient.patch(url, data, config);
  },
};

export default apiClient;
