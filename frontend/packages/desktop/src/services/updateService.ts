/**
 * EvoLoop 更新服务
 * 
 * 更新检查策略:
 * 1. 应用启动时检查 (延迟 3 秒，避免影响启动速度)
 * 2. 定时检查 (每 24 小时一次)
 * 3. 手动检查 (用户在关于页面点击)
 * 4. 网络恢复时检查 (从离线状态恢复)
 * 5. 应用从后台恢复时检查 (可选)
 */

import type { UpdateCheckResult } from '@/hooks/useVersion';
import versionInfo from '@/version.json';

/** 更新检查配置 */
interface UpdateCheckConfig {
  /** MC API 基础 URL */
  baseUrl: string;
  /** 检查间隔 (毫秒)，默认 24 小时 */
  checkInterval: number;
  /** 启动后延迟检查时间 (毫秒)，默认 3 秒 */
  startupDelay: number;
  /** 是否启用启动检查 */
  enableStartupCheck: boolean;
  /** 是否启用定时检查 */
  enableScheduledCheck: boolean;
  /** 是否启用网络恢复检查 */
  enableNetworkRecoveryCheck: boolean;
}

/** 更新检查记录 */
interface UpdateCheckRecord {
  lastCheckTime: number;
  lastVersion: string;
  skippedVersion?: string;
}

/** 默认配置 */
const DEFAULT_CONFIG: UpdateCheckConfig = {
  baseUrl: import.meta.env.VITE_EVOCLOUD_MEMBER_BASE_URL || 'https://evoloop.cn/member',
  checkInterval: 24 * 60 * 60 * 1000, // 24 小时
  startupDelay: 3000, // 3 秒
  enableStartupCheck: true,
  enableScheduledCheck: true,
  enableNetworkRecoveryCheck: true,
};

/** 存储键 */
const STORAGE_KEY = 'evoloop_update_check';
const DEVICE_ID_KEY = 'evoloop_device_id';

class UpdateService {
  private config: UpdateCheckConfig;
  private scheduledTimer: number | null = null;
  private isInitialized = false;

  constructor(config: Partial<UpdateCheckConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  /**
   * 初始化更新服务
   * - 注册网络状态监听
   * - 启动定时检查
   * - 延迟执行启动检查
   */
  init(): void {
    if (this.isInitialized) return;
    this.isInitialized = true;

    console.log('[UpdateService] 初始化更新服务');

    // 1. 启动时检查 (延迟执行，避免影响应用启动速度)
    if (this.config.enableStartupCheck) {
      this.scheduleStartupCheck();
    }

    // 2. 定时检查
    if (this.config.enableScheduledCheck) {
      this.startScheduledCheck();
    }

    // 3. 网络恢复检查
    if (this.config.enableNetworkRecoveryCheck) {
      this.setupNetworkRecoveryCheck();
    }
  }

  /**
   * 销毁更新服务
   */
  destroy(): void {
    if (this.scheduledTimer) {
      window.clearInterval(this.scheduledTimer);
      this.scheduledTimer = null;
    }
    this.isInitialized = false;
  }

  /**
   * 计划启动时检查
   * 延迟执行，避免影响应用启动速度
   */
  private scheduleStartupCheck(): void {
    // 检查是否需要跳过 (24 小时内已检查过)
    const record = this.getCheckRecord();
    const now = Date.now();
    
    if (record && now - record.lastCheckTime < this.config.checkInterval) {
      console.log('[UpdateService] 跳过启动检查，上次检查:', new Date(record.lastCheckTime).toLocaleString());
      return;
    }

    console.log(`[UpdateService] 计划在 ${this.config.startupDelay}ms 后执行启动检查`);

    window.setTimeout(() => {
      this.performCheck('startup').catch(console.error);
    }, this.config.startupDelay);
  }

  /**
   * 启动定时检查
   */
  private startScheduledCheck(): void {
    // 每小时检查一次是否需要执行版本检查
    this.scheduledTimer = window.setInterval(() => {
      const record = this.getCheckRecord();
      const now = Date.now();

      if (!record || now - record.lastCheckTime >= this.config.checkInterval) {
        console.log('[UpdateService] 执行定时更新检查');
        this.performCheck('scheduled').catch(console.error);
      }
    }, 60 * 60 * 1000); // 每小时检查一次记录
  }

  /**
   * 设置网络恢复检查
   */
  private setupNetworkRecoveryCheck(): void {
    let wasOffline = !navigator.onLine;

    window.addEventListener('online', () => {
      if (wasOffline) {
        console.log('[UpdateService] 网络恢复，执行更新检查');
        // 延迟 1 秒，确保网络真正稳定
        window.setTimeout(() => {
          this.performCheck('network_recovery').catch(console.error);
        }, 1000);
      }
      wasOffline = false;
    });

    window.addEventListener('offline', () => {
      wasOffline = true;
    });
  }

  /**
   * 执行更新检查
   * @param trigger 触发方式
   * @param force 是否强制检查 (忽略间隔限制)
 */
  async performCheck(
    trigger: 'startup' | 'scheduled' | 'manual' | 'network_recovery' = 'manual',
    force = false
  ): Promise<UpdateCheckResult> {
    console.log(`[UpdateService] 执行更新检查 (触发方式: ${trigger})`);

    // 检查网络状态
    if (!navigator.onLine) {
      console.log('[UpdateService] 离线状态，跳过检查');
      return { hasUpdate: false };
    }

    // 非强制检查时，检查间隔
    if (!force) {
      const record = this.getCheckRecord();
      const now = Date.now();
      
      if (record && now - record.lastCheckTime < this.config.checkInterval) {
        console.log('[UpdateService] 检查间隔未到，跳过');
        return { hasUpdate: false };
      }
    }

    try {
      const result = await this.callCheckApi();
      
      // 更新检查记录
      this.updateCheckRecord(result.latestVersion || versionInfo.version);

      if (result.hasUpdate) {
        console.log('[UpdateService] 发现新版本:', result.latestVersion);
        
        // 检查是否被用户跳过
        const record = this.getCheckRecord();
        if (record?.skippedVersion === result.latestVersion && !force) {
          console.log('[UpdateService] 用户已跳过此版本');
          return { hasUpdate: false };
        }
      }

      return result;
    } catch (error) {
      console.error('[UpdateService] 更新检查失败:', error);
      return { hasUpdate: false };
    }
  }

  /**
   * 调用 MC 版本检查 API
   */
  private async callCheckApi(): Promise<UpdateCheckResult> {
    const deviceId = this.getDeviceId();
    const platform = this.getPlatform();
    const arch = this.getArchitecture();
    const osVersion = this.getOSVersion();

    const response = await fetch(`${this.config.baseUrl}/api/evoloop/version/check`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        app_type: 'desktop',
        platform: platform,
        arch: arch,
        version: versionInfo.version,
        build_number: versionInfo.buildNumber,
        device_id: deviceId,
        channel: versionInfo.stage === 'stable' ? 'stable' : 'beta',
        os_version: osVersion,
      }),
    });

    if (!response.ok) {
      throw new Error(`API 请求失败: ${response.status}`);
    }

    const apiResult = await response.json();
    
    if (apiResult.code !== 0) {
      throw new Error(apiResult.message || 'API 返回错误');
    }

    const data = apiResult.data;

    return {
      hasUpdate: data.has_update || false,
      latestVersion: data.version,
      downloadUrl: data.download_url,
      releaseNotes: data.release_notes,
      isForceUpdate: data.update_type === 2, // 强制更新
    };
  }

  /**
   * 上报更新状态
   * @param action 更新动作
   * @param progress 进度 (0-100)
   * @param errorMessage 错误信息
   */
  async reportUpdateStatus(
    action: 'download_start' | 'download_complete' | 'install_start' | 'install_success' | 'install_failed',
    toVersion: string,
    progress?: number,
    errorMessage?: string
  ): Promise<void> {
    try {
      const deviceId = this.getDeviceId();
      
      await fetch(`${this.config.baseUrl}/api/evoloop/version/report`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          device_id: deviceId,
          app_type: 'desktop',
          platform: this.getPlatform(),
          arch: this.getArchitecture(),
          os_version: this.getOSVersion(),
          from_version: versionInfo.version,
          to_version: toVersion,
          action: action,
          progress: progress,
          error_message: errorMessage,
        }),
      });
    } catch (error) {
      console.error('[UpdateService] 上报更新状态失败:', error);
    }
  }

  /**
   * 跳过指定版本
   */
  skipVersion(version: string): void {
    const record = this.getCheckRecord();
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      ...record,
      skippedVersion: version,
    }));
  }

  /**
   * 获取设备 ID
   */
  private getDeviceId(): string {
    let deviceId = localStorage.getItem(DEVICE_ID_KEY);
    
    if (!deviceId) {
      deviceId = this.generateDeviceId();
      localStorage.setItem(DEVICE_ID_KEY, deviceId);
    }
    
    return deviceId;
  }

  /**
   * 生成设备 ID
   */
  private generateDeviceId(): string {
    const timestamp = Date.now().toString(36);
    const random = Math.random().toString(36).substring(2, 10);
    return `evo_${timestamp}_${random}`;
  }

  /**
   * 获取平台
   */
  private getPlatform(): string {
    const userAgent = navigator.userAgent.toLowerCase();
    
    if (userAgent.includes('win')) return 'windows';
    if (userAgent.includes('mac')) return 'macos';
    if (userAgent.includes('linux')) return 'linux';
    
    return 'unknown';
  }

  /**
   * 获取 CPU 架构
   */
  private getArchitecture(): string {
    // 优先使用新的 API (Chrome 90+)
    // @ts-ignore
    if (navigator.userAgentData?.architecture) {
      // @ts-ignore
      const arch = navigator.userAgentData.architecture;
      const archMap: Record<string, string> = {
        'x86': 'x86_64',
        'x86_64': 'x86_64',
        'arm': 'arm64',
        'arm64': 'arm64',
        'aarch64': 'aarch64',
      };
      return archMap[arch] || 'x86_64';
    }

    // 从 User-Agent 推断
    const userAgent = navigator.userAgent.toLowerCase();
    
    if (userAgent.includes('arm64') || userAgent.includes('aarch64')) {
      return 'arm64';
    }
    
    if (userAgent.includes('mac') && (userAgent.includes('arm64') || userAgent.includes('apple silicon'))) {
      return 'arm64';
    }
    
    return 'x86_64';
  }

  /**
   * 获取操作系统版本
   */
  private getOSVersion(): string {
    const userAgent = navigator.userAgent;
    
    // Windows 版本
    const windowsMatch = userAgent.match(/Windows NT (\d+\.\d+)/);
    if (windowsMatch) {
      const versionMap: Record<string, string> = {
        '10.0': '10',
        '6.3': '8.1',
        '6.2': '8',
        '6.1': '7',
      };
      return versionMap[windowsMatch[1]] || windowsMatch[1];
    }
    
    // macOS 版本
    const macMatch = userAgent.match(/Mac OS X (\d+[._]\d+[._]?\d*)/);
    if (macMatch) {
      return macMatch[1].replace(/_/g, '.');
    }
    
    return '';
  }

  /**
   * 获取检查记录
   */
  private getCheckRecord(): UpdateCheckRecord | null {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return null;
    
    try {
      return JSON.parse(stored);
    } catch {
      return null;
    }
  }

  /**
   * 更新检查记录
   */
  private updateCheckRecord(version: string): void {
    const record: UpdateCheckRecord = {
      lastCheckTime: Date.now(),
      lastVersion: version,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(record));
  }
}

// 导出单例实例
export const updateService = new UpdateService();

export default UpdateService;
