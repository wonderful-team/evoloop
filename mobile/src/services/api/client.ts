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
    // 从 authStore 获取 token（实时状态），若未就绪则回退 AsyncStorage
    let token = useAuthStore.getState().token;
    if (!token) {
      token = await AsyncStorage.getItem('token');
    }

    // 判断是否为 Gateway 请求（Gateway 使用 Authorization header）
    const isGatewayRequest = (config.url || '').startsWith('/gateway/');

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

    console.log(`API Request: ${config.method?.toUpperCase()} ${config.url}`);

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

        // 清除登录状态并提示用户
        useAuthStore.getState().logout();
        isRefreshing = false;
        showGlobalToast('登录已过期，请重新登录', 'error');

        // 返回 rejected promise，让调用方捕获错误
        return Promise.reject(new Error('登录已过期，请重新登录'));
      }
    }

    // 若请求标记为需要完整 response，跳过解包
    if ((response.config as any)._rawResponse) {
      return response;
    }

    // 统一返回 data 字段
    return response.data;
  },
  async (error: AxiosError) => {
    const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean };

    console.error('API Error:', error.response?.status, error.response?.data);

    // 401 错误处理（清除状态并提示用户，由页面根据 isLoggedIn 状态自行更新 UI）
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
        // 清除登录状态并提示用户
        useAuthStore.getState().logout();
        showGlobalToast('登录已过期，请重新登录', 'error');
        const appError = handleApiError(error);
        return Promise.reject(appError);
      } catch (refreshError) {
        useAuthStore.getState().logout();
        showGlobalToast('登录已过期，请重新登录', 'error');
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
      const benefitCheckData = typeof responseData === 'object' && responseData !== null
        ? { ...responseData, status: 403 }
        : { status: 403 };
      if (checkIsBenefitError(benefitCheckData)) {
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

// SSE 流式请求配置
export interface SSEOptions {
  onChunk: (chunk: string) => void;
  onDone?: () => void;
  onError?: (error: Error) => void;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

/**
 * SSE 流式请求（使用 XMLHttpRequest，React Native 中比 fetch + ReadableStream 更可靠）
 * 解析 OpenAI 格式的 SSE data: {...} 行
 */
async function fetchSSE(url: string, body: any, options: SSEOptions): Promise<void> {
  const token = useAuthStore.getState().token || await AsyncStorage.getItem('token');

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    let receivedLength = 0;
    let lineBuffer = '';

    xhr.open('POST', `${API_CONFIG.baseURL}${url}`);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.setRequestHeader('Accept', 'text/event-stream');
    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    }
    // 透传额外 headers（如 X-Thread-ID, X-Device-Key）
    if (options.headers) {
      Object.entries(options.headers).forEach(([key, value]) => {
        xhr.setRequestHeader(key, value);
      });
    }

    // AbortController 支持
    if (options.signal) {
      const onAbort = () => {
        xhr.abort();
      };
      if (options.signal.aborted) {
        onAbort();
        return;
      }
      options.signal.addEventListener('abort', onAbort);
      xhr.addEventListener('loadend', () => {
        options.signal?.removeEventListener('abort', onAbort);
      });
    }

    // 核心：使用 onprogress 处理流式数据（RN 中比 onreadystatechange 更可靠）
    const processNewData = () => {
      const newData = xhr.responseText.slice(receivedLength);
      receivedLength = xhr.responseText.length;
      if (!newData) return;
      console.log('[fetchSSE] onprogress newData length:', newData.length, 'total:', receivedLength);

      lineBuffer += newData;

      // 按行分割，保留未完成的最后一行
      const lines = lineBuffer.split('\n');
      lineBuffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data: ')) continue;

        const data = trimmed.slice(6); // 去掉 'data: ' 前缀
        if (data === '[DONE]') {
          options.onDone?.();
          resolve();
          return;
        }

        try {
          const parsed = JSON.parse(data);
          const content = parsed.choices?.[0]?.delta?.content;
          if (content) {
            console.log('[fetchSSE] onChunk:', content);
            options.onChunk(content);
          }
        } catch {
          // 忽略无法解析的行
        }
      }
    };

    xhr.onprogress = processNewData;

    xhr.onreadystatechange = () => {
      if (xhr.readyState === 4) {
        // 请求完成但状态码错误
        if (xhr.status < 200 || xhr.status >= 300) {
          let errMsg = `HTTP ${xhr.status}`;
          try {
            const errData = JSON.parse(xhr.responseText);
            errMsg = errData.message || errData.error?.message || errMsg;
          } catch {
            // 非 JSON 错误响应
          }
          reject(new Error(errMsg));
          return;
        }

        // 处理最后一批数据（onprogress 可能漏掉）
        processNewData();

        // 处理 buffer 中剩余的内容
        if (lineBuffer.trim().startsWith('data: ')) {
          const data = lineBuffer.trim().slice(6);
          if (data !== '[DONE]') {
            try {
              const parsed = JSON.parse(data);
              const content = parsed.choices?.[0]?.delta?.content;
              if (content) options.onChunk(content);
            } catch {
              // 忽略
            }
          }
        }

        options.onDone?.();
        resolve();
      }
    };

    xhr.onerror = () => {
      reject(new Error('SSE 请求失败'));
    };

    xhr.ontimeout = () => {
      reject(new Error('SSE 请求超时'));
    };

    xhr.onabort = () => {
      options.onDone?.();
      resolve();
    };

    xhr.send(JSON.stringify(body));
  });
}

// 封装请求方法（返回 response.data）
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

  /** SSE 流式请求 */
  fetchSSE,
};

// 原始请求方法（返回完整 AxiosResponse，用于需要 headers/status 的场景）
export const apiRaw = {
  get: <T = any>(url: string, config?: AxiosRequestConfig): Promise<AxiosResponse<T>> => {
    return apiClient.get(url, { ...config, _rawResponse: true } as AxiosRequestConfig);
  },

  post: <T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<AxiosResponse<T>> => {
    return apiClient.post(url, data, { ...config, _rawResponse: true } as AxiosRequestConfig);
  },
};

export default apiClient;

// 导出配置供其他模块使用
export { API_CONFIG };
