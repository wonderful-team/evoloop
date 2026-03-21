/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string
  readonly VITE_EVOCLOUD_MEMBER_URL: string
  /**
   * 启动页面调试模式
   * - "true": 显示终端窗口（带日志输出）
   * - "false": 显示简洁 LOGO + 进度条
   * @default "false"
   */
  readonly VITE_STARTUP_DEBUG_MODE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
