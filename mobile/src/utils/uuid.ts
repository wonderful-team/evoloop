// UUID 生成工具

/**
 * 生成 UUID v4
 * @returns UUID 字符串
 */
export function generateUUID(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * 生成短 ID（用于会话 ID 等）
 * @param length ID 长度
 * @returns 短 ID 字符串
 */
export function generateShortId(length: number = 8): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let result = '';
  for (let i = 0; i < length; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

/**
 * 生成时间戳 ID
 * @returns 时间戳 ID 字符串
 */
export function generateTimestampId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}
