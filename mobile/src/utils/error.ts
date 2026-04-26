// 通用错误处理工具

export interface QuotaError extends Error {
  __quota_exhausted: boolean;
}

export function isQuotaError(error: unknown): error is QuotaError {
  return error instanceof Error && (error as QuotaError).__quota_exhausted === true;
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === 'string') return error;
  return '未知错误';
}

export function isErrorWithProperty(error: unknown, prop: string): boolean {
  return error instanceof Error && prop in error;
}
