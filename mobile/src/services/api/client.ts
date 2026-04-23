// Axios API 客户端

import axios, { AxiosError, AxiosRequestConfig, AxiosResponse } from 'axios';
import { API_CONFIG } from '@/constants/config';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { handleApiError, isAuthError } from '@/utils/error';
import { checkIsBenefitError, handleBenefitError, convertToBenefitError } from '@/utils/subscriptionErrors';
import { showGlobalToast } from '@/contexts/ToastContext';
import { useAuthStore } from '@/stores/authStore';

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
    // 从 authStore 获取 token（实时状态）
    const token = useAuthStore.getState().token;

    // URL 前缀处理 - 根据路径前缀设置正确的 baseURL
    const originalUrl = config.url || '';

    // 判断是否为 Gateway 请求（Gateway 使用 Authorization header）
    const isGatewayRequest = originalUrl.startsWith('/gateway');

    if (token) {
      if (isGatewayRequest) {
        // Gateway 使用 Authorization header
        config.headers.Authorization = `Bearer ${token}`;
        console.log('[API] Token set in header for Gateway:', token.substring(0, 20) + '...');
      } else {
        // Member 等其他服务使用 query parameter（参考原 mobile 项目）
        config.params = {
          ...config.params,
          token,
        };
        console.log('[API] Token set as query param:', token.substring(0, 20) + '...');
      }
    } else {
      console.log('[API] No token available');
    }

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

// Token 过期的业务错误码（MC 返回）
const TOKEN_EXPIRED_CODES = [-10010, -10011];

// 响应拦截器
apiClient.interceptors.response.use(
  (response: AxiosResponse) => {
    // 统一返回 data 字段
    console.log(`API Response: ${response.config.url}`, response.data);

    // 检查业务错误码 - Token 过期
    const data = response.data;
    if (data && TOKEN_EXPIRED_CODES.includes(data.code)) {
      console.log('[API] Token expired (business code):', data.code, data.message);

      // 避免重复处理
      const originalRequest = response.config as AxiosRequestConfig & { _retry?: boolean };
      if (!originalRequest._retry && !isRefreshing) {
        originalRequest._retry = true;
        isRefreshing = true;

        // 清除登录状态，由页面根据 isLoggedIn 状态自行更新 UI
        useAuthStore.getState().logout();
        isRefreshing = false;

        // 返回一个永远不会 resolve 的 promise，阻止后续处理
        return new Promise(() => {});
      }
    }

    return response.data;
  },
  async (error: AxiosError) => {
    const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean };

    console.error('API Error:', error.response?.status, error.response?.data);

    // 401 错误处理（不显示 Toast，不强制跳转，由页面根据 isLoggedIn 状态自行更新 UI）
    console.log('[API] Response error:', error.response?.status, error.response?.data);
    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        // 等待 token 刷新
        return new Promise((resolve) => {
          subscribeTokenRefresh((token: string) => {
            // 判断是否为 Gateway 请求
            const isGatewayRequest = originalRequest.url?.startsWith('/gateway');
            if (isGatewayRequest) {
              // Gateway 使用 Authorization header
              originalRequest.headers = originalRequest.headers || {};
              originalRequest.headers.Authorization = `Bearer ${token}`;
            } else {
              // Member 等其他服务使用 query parameter
              originalRequest.params = {
                ...originalRequest.params,
                token,
              };
            }
            resolve(apiClient(originalRequest));
          });
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        // 清除登录状态，由页面根据 isLoggedIn 状态自行更新 UI
        useAuthStore.getState().logout();
        const appError = handleApiError(error);
        return Promise.reject(appError);
      } catch (refreshError) {
        useAuthStore.getState().logout();
        return Promise.reject(handleApiError(refreshError));
      } finally {
        isRefreshing = false;
      }
    }

    // 处理 API 错误并显示 Toast（非 401 错误）
    const appError = handleApiError(error);
    if (appError.message) {
      showGlobalToast(appError.message, 'error');
    }

    if (!originalRequest) {
      return Promise.reject(appError);
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

    return Promise.reject(appError);
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

// 导出配置供其他模块使用
export { API_CONFIG };
