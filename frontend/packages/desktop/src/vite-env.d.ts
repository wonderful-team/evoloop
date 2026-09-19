/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string
  readonly VITE_EVOCLOUD_MEMBER_BASE_URL: string
  /**
   * 自主值守演示模式
   * - "true": 使用内置演示运行时
   * - "false"/未设置: 读取真实任务队列
   */
  readonly VITE_DUTY_DEMO?: string
  /**
   * 启动页面调试模式
   * - "true": 显示终端窗口（带日志输出）
   * - "false": 显示简洁 LOGO + 进度条
   * @default "false"
   */
  readonly VITE_STARTUP_DEBUG_MODE?: string
  /**
   * 高德地图 JS API Key
   * 申请地址: https://console.amap.com/
   */
  readonly VITE_AMAP_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
