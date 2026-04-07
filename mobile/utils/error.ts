// 错误处理工具

import { AxiosError } from 'axios';

// 应用错误类
export class AppError extends Error {
  code: string;
  statusCode?: number;
  
  constructor(message: string, code: string, statusCode?: number) {
    super(message);
    this.name = 'AppError';
    this.code = code;
    this.statusCode = statusCode;
  }
}

// 错误代码枚举
export const ErrorCode = {
  // 网络错误
  NETWORK_ERROR: 'NETWORK_ERROR',
  TIMEOUT_ERROR: 'TIMEOUT_ERROR',
  
  // 认证错误
  UNAUTHORIZED: 'UNAUTHORIZED',
  TOKEN_EXPIRED: 'TOKEN_EXPIRED',
  
  // 业务错误
  VALIDATION_ERROR: 'VALIDATION_ERROR',
  BUSINESS_ERROR: 'BUSINESS_ERROR',
  
  // 系统错误
  SERVER_ERROR: 'SERVER_ERROR',
  UNKNOWN_ERROR: 'UNKNOWN_ERROR',
} as const;

// HTTP 状态码对应的错误消息
const HTTP_ERROR_MESSAGES: Record<number, string> = {
  400: '请求参数错误',
  401: '登录已过期，请重新登录',
  403: '没有权限执行此操作',
  404: '请求的资源不存在',
  500: '服务器内部错误',
  502: '网关错误',
  503: '服务暂时不可用',
};

// 处理 API 错误
export const handleApiError = (error: unknown): AppError => {
  if (error instanceof AppError) {
    return error;
  }
  
  if (error instanceof AxiosError) {
    const status = error.response?.status;
    const message = error.response?.data?.message;
    
    if (status === 401) {
      return new AppError(message || '登录已过期', ErrorCode.UNAUTHORIZED, 401);
    }
    
    if (status) {
      return new AppError(
        message || HTTP_ERROR_MESSAGES[status] || '请求失败',
        ErrorCode.BUSINESS_ERROR,
        status
      );
    }
    
    if (error.code === 'ECONNABORTED') {
      return new AppError('请求超时，请检查网络', ErrorCode.TIMEOUT_ERROR);
    }
    
    return new AppError('网络错误，请检查网络连接', ErrorCode.NETWORK_ERROR);
  }
  
  if (error instanceof Error) {
    return new AppError(error.message, ErrorCode.UNKNOWN_ERROR);
  }
  
  return new AppError('未知错误', ErrorCode.UNKNOWN_ERROR);
};

// 获取用户友好的错误消息
export const getErrorMessage = (error: unknown): string => {
  const appError = handleApiError(error);
  return appError.message;
};

// 是否需要重新登录
export const isAuthError = (error: unknown): boolean => {
  const appError = handleApiError(error);
  return appError.code === ErrorCode.UNAUTHORIZED || 
         appError.code === ErrorCode.TOKEN_EXPIRED;
};
