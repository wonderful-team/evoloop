// 通用错误处理工具

import i18n from '@/locales';

export interface QuotaError extends Error {
  __quota_exhausted: boolean;
}

export function isQuotaError(error: unknown): error is QuotaError {
  return error instanceof Error && (error as QuotaError).__quota_exhausted === true;
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === 'string') return error;
  return i18n.t('error.unknown');
}

export function handleApiError(error: unknown): Error {
  if (error instanceof Error) return error;
  if (typeof error === 'string') return new Error(error);
  return new Error(i18n.t('error.unknown'));
}

export function isAuthError(error: unknown): boolean {
  if (error instanceof Error) {
    const msg = error.message || '';
    return /unauthorized|未登录|token|401|403/i.test(msg);
  }
  return false;
}

export function isErrorWithProperty(error: unknown, prop: string): boolean {
  return error instanceof Error && prop in error;
}
