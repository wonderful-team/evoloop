// 通用错误处理工具

import { AxiosError } from 'axios';
import i18n from '@/locales';

export interface QuotaError extends Error {
  __quota_exhausted: boolean;
}

export function isQuotaError(error: unknown): error is QuotaError {
  return error instanceof Error && (error as QuotaError).__quota_exhausted === true;
}

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

  // 权益/订阅错误
  BENEFIT_REQUIRED: 'BENEFIT_REQUIRED',
  SUBSCRIPTION_REQUIRED: 'SUBSCRIPTION_REQUIRED',

  // 系统错误
  SERVER_ERROR: 'SERVER_ERROR',
  UNKNOWN_ERROR: 'UNKNOWN_ERROR',
} as const;

export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === 'string') {
    return error;
  }
  return i18n.t('error.unknown');
}

function getHttpErrorMessage(status: number, serverMessage?: string): string {
  if (serverMessage) {
    return serverMessage;
  }
  const key = `api.httpErrors.${status}`;
  const translated = i18n.t(key);
  if (translated !== key) {
    return translated;
  }
  return i18n.t('api.httpErrors.default', { status });
}

export function handleApiError(error: unknown): AppError {
  if (error instanceof AppError) {
    return error;
  }

  if (error instanceof AxiosError) {
    const status = error.response?.status;
    const data = error.response?.data;
    const serverMessage = data?.message || data?.data?.message;

    if (status === 401) {
      return new AppError(
        serverMessage || i18n.t('api.httpErrors.401'),
        ErrorCode.UNAUTHORIZED,
        401
      );
    }

    if (status === 403) {
      return new AppError(
        getHttpErrorMessage(status, serverMessage),
        ErrorCode.BUSINESS_ERROR,
        403
      );
    }

    if (status) {
      return new AppError(
        getHttpErrorMessage(status, serverMessage),
        ErrorCode.BUSINESS_ERROR,
        status
      );
    }

    if (error.code === 'ECONNABORTED') {
      return new AppError(i18n.t('api.errors.timeout'), ErrorCode.TIMEOUT_ERROR);
    }

    return new AppError(i18n.t('api.errors.networkError'), ErrorCode.NETWORK_ERROR);
  }

  if (error instanceof Error) {
    return new AppError(error.message, ErrorCode.UNKNOWN_ERROR);
  }

  if (typeof error === 'string') {
    return new AppError(error, ErrorCode.UNKNOWN_ERROR);
  }

  return new AppError(i18n.t('error.unknown'), ErrorCode.UNKNOWN_ERROR);
}

export function isAuthError(error: unknown): boolean {
  if (error instanceof AppError) {
    return error.code === ErrorCode.UNAUTHORIZED || error.code === ErrorCode.TOKEN_EXPIRED;
  }
  if (error instanceof Error) {
    const msg = error.message || '';
    return /unauthorized|未登录|过期|token|401|403/i.test(msg);
  }
  return false;
}

export function isErrorWithProperty(error: unknown, prop: string): boolean {
  return error instanceof Error && prop in error;
}
