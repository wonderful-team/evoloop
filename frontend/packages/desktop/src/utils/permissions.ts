import { ask, message } from '@tauri-apps/plugin-dialog'

/**
 * 检查麦克风权限状态
 */
export async function checkMicrophonePermission(): Promise<PermissionState> {
  try {
    // 使用 Permissions API (如果可用)
    if ('permissions' in navigator) {
      try {
        const result = await navigator.permissions.query({ 
          name: 'microphone' as PermissionName 
        })
        return result.state
      } catch {
        // 某些浏览器不支持 microphone 权限查询
      }
    }
    
    // 直接测试麦克风访问
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    stream.getTracks().forEach(track => track.stop())
    return 'granted'
  } catch (err: any) {
    if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
      return 'denied'
    }
    if (err.name === 'NotFoundError') {
      return 'prompt' // 可能还没请求过
    }
    return 'prompt'
  }
}

/**
 * 请求麦克风权限
 */
export async function requestMicrophonePermission(): Promise<boolean> {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    stream.getTracks().forEach(track => track.stop())
    return true
  } catch (err: any) {
    console.error('Microphone permission denied:', err)
    return false
  }
}

/**
 * 显示权限引导对话框
 */
export async function showPermissionGuide(): Promise<void> {
  const isMac = navigator.platform.toLowerCase().includes('mac')
  const isWindows = navigator.platform.toLowerCase().includes('win')
  
  let instructions = ''
  
  if (isMac) {
    instructions = `请在系统设置中允许麦克风访问：

1. 打开 系统设置 > 隐私与安全性 > 麦克风
2. 找到并勾选 "EvoLoop" 应用
3. 重启应用后重试`
  } else if (isWindows) {
    instructions = `请在 Windows 设置中允许麦克风访问：

1. 打开 设置 > 隐私 > 麦克风
2. 允许应用访问麦克风
3. 在应用列表中找到并允许 "EvoLoop"`
  } else {
    instructions = `请在系统设置中允许应用访问麦克风。`
  }

  await message(instructions, {
    title: '需要麦克风权限',
    kind: 'info'
  })
}

/**
 * 检查并请求麦克风权限（带引导）
 */
export async function ensureMicrophonePermission(): Promise<boolean> {
  const state = await checkMicrophonePermission()
  
  if (state === 'granted') {
    return true
  }
  
  if (state === 'prompt') {
    // 还没请求过，直接请求
    const granted = await requestMicrophonePermission()
    if (!granted) {
      await showPermissionGuide()
    }
    return granted
  }
  
  // 被拒绝，显示引导
  const shouldShowGuide = await ask(
    '麦克风权限被拒绝。是否查看如何开启权限？',
    { title: '需要麦克风权限', kind: 'warning' }
  )
  
  if (shouldShowGuide) {
    await showPermissionGuide()
  }
  
  return false
}

/**
 * 检查通知权限
 */
export async function checkNotificationPermission(): Promise<boolean> {
  if (!('Notification' in window)) {
    return false
  }
  
  if (Notification.permission === 'granted') {
    return true
  }
  
  if (Notification.permission === 'default') {
    const permission = await Notification.requestPermission()
    return permission === 'granted'
  }
  
  return false
}
