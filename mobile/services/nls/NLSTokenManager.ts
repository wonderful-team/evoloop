// NLS Token 管理器
// 从 Gateway 获取临时 Token（推荐，安全）

// Gateway 地址（根据实际部署修改）
const GATEWAY_URL = process.env.EXPO_PUBLIC_GATEWAY_URL || 'https://gateway.evoloop.develop-assistant.cn';

interface TokenResponse {
  token: string;
  expireTime: number; // 过期时间戳
}

class NLSTokenManager {
  private token: string = '';
  private expireTime: number = 0;

  // 从 Gateway 获取临时 Token
  async fetchTokenFromGateway(): Promise<string> {
    try {
      // TODO: 确认 Gateway 的 Token 接口路径
      const response = await fetch(`${GATEWAY_URL}/nls/token`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          // 如果需要认证，添加 Authorization header
          // 'Authorization': `Bearer ${await getAuthToken()}`,
        },
      });

      if (!response.ok) {
        throw new Error(`获取 Token 失败: ${response.status}`);
      }

      const data: TokenResponse = await response.json();
      this.token = data.token;
      this.expireTime = data.expireTime;

      return this.token;
    } catch (error) {
      console.error('从 Gateway 获取 NLS Token 失败:', error);
      // 降级：如果 Gateway 不可用，可以尝试本地生成（仅测试用，生产环境不推荐）
      // return this.generateLocalToken();
      throw error;
    }
  }

  // 获取有效 Token
  async getValidToken(): Promise<string> {
    // 如果 Token 还有 5 分钟以上有效期，直接返回
    if (this.token && this.expireTime - Date.now() > 5 * 60 * 1000) {
      return this.token;
    }

    // 否则重新获取
    return this.fetchTokenFromGateway();
  }

  // 清除 Token
  clearToken(): void {
    this.token = '';
    this.expireTime = 0;
  }
}

export const nlsTokenManager = new NLSTokenManager();
